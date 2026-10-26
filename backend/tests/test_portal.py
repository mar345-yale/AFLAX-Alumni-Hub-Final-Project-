"""Alumni map/roster, privacy, schedule, RSVPs, photos, explorer, and migrations."""

import io

from PIL import Image

import db


def test_alumni_filters_and_location_click(client, admin):
    everyone = client.get("/api/alumni", headers=admin).json()
    assert everyone["total"] >= 100
    names = [(m["last_name"].lower(), m["first_name"].lower()) for m in everyone["roster"]]
    assert names == sorted(names)

    pilots = client.get("/api/alumni", headers=admin, params={"status": "Active Duty", "afsc": "92T0"}).json()
    assert pilots["total"] > 0 and all(m["afsc"] == "92T0" for m in pilots["roster"])

    hill = client.get("/api/alumni", headers=admin, params={"location": "Hill AFB, UT"}).json()
    assert hill["roster"] and all(m["location"] == "Hill AFB, UT" for m in hill["roster"])
    assert len(hill["pins"]) == len(everyone["pins"])  # a clicked pin narrows only the roster


def test_hidden_phone_is_hidden_from_members_but_not_the_board(client, admin, approved_member):
    headers, _, user_id = approved_member
    profile = {"first_name": "Private", "last_name": "Person", "grad_year": "2015", "status": "Civilian",
               "city": "Denver, CO", "phone": "(303) 555-0199", "show_phone": "false"}
    assert client.put("/api/me", headers=headers, data=profile).json()["show_phone"] is False

    other = client.post("/api/auth/signup", data={
        "email": "viewer@example.com", "confirm_email": "viewer@example.com",
        "password": "goFalcons1", "confirm_password": "goFalcons1", "first_name": "View",
        "last_name": "Er", "grad_year": "2028", "status": "Cadet"})
    assert other.status_code == 201
    vid = next(a["id"] for a in client.get("/api/admin/accounts", headers=admin).json()["accounts"]
               if a["email"] == "viewer@example.com")
    client.post(f"/api/admin/accounts/{vid}/approve", headers=admin)
    viewer = {"Authorization": "Bearer " + client.post(
        "/api/auth/login", json={"email": "viewer@example.com", "password": "goFalcons1"}).json()["token"]}

    def phone_seen_by(h):
        roster = client.get("/api/alumni", headers=h).json()["roster"]
        return next(m["phone"] for m in roster if m["id"] == user_id)

    assert phone_seen_by(viewer) is None
    assert phone_seen_by(admin) == "(303) 555-0199"


def test_tailgate_rsvp_toggle(client, admin, approved_member):
    headers, _, _ = approved_member
    tailgate = next(t for g in client.get("/api/schedule", headers=headers).json()["games"] for t in g["tailgates"])
    before = tailgate["rsvp_count"]
    assert client.post(f"/api/tailgates/{tailgate['id']}/rsvp", headers=headers).status_code == 204
    assert client.post(f"/api/tailgates/{tailgate['id']}/rsvp", headers=headers).status_code == 204  # idempotent

    def current():
        return next(t for g in client.get("/api/schedule", headers=headers).json()["games"]
                    for t in g["tailgates"] if t["id"] == tailgate["id"])

    assert current()["rsvp_count"] == before + 1 and current()["going"] is True
    client.delete(f"/api/tailgates/{tailgate['id']}/rsvp", headers=headers)
    assert current()["rsvp_count"] == before and current()["going"] is False


def test_photo_upload_strips_metadata_and_requires_signed_link(client, approved_member):
    headers, _, _ = approved_member
    img = Image.new("RGB", (1600, 1200), "blue")
    exif = img.getexif()
    exif[0x010F] = "iPhone"
    gps = exif.get_ifd(0x8825)
    gps[2] = (40.0, 26.0, 46.0)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    profile = {"first_name": "Photo", "last_name": "Test", "grad_year": "2015", "status": "Civilian", "city": "Denver, CO"}

    me = client.put("/api/me", headers=headers, data=profile, files={"photo": ("p.jpg", buf.getvalue(), "image/jpeg")}).json()
    served = client.get(me["photo_url"])
    assert served.status_code == 200
    out = Image.open(io.BytesIO(served.content))
    assert max(out.size) <= 512 and len(out.getexif()) == 0

    assert client.get(me["photo_url"].replace("sig=", "sig=0")).status_code == 404
    bad = client.put("/api/me", headers=headers, data=profile, files={"photo": ("x.jpg", b"<script>", "image/jpeg")})
    assert bad.status_code == 422


def test_board_can_add_games_and_tailgates(client, admin):
    game = client.post("/api/games", headers=admin, json={
        "game_date": "2027-02-06", "time_label": "12:00 PM", "home_away": "Away",
        "opponent": "Denver", "location": "Denver, CO"}).json()
    assert game["mapped"] is True
    t = client.post("/api/tailgates", headers=admin, json={"game_id": game["id"], "title": "Mile High Tailgate", "location": "Lot C"})
    assert t.status_code == 201
    schedule = client.get("/api/schedule", headers=admin).json()
    assert schedule["next_game_id"] == game["id"]


def test_explorer_endpoints(client, admin):
    afscs = client.get("/api/explore/afscs", headers=admin).json()
    assert len(afscs) == 36 and all("overview" in a for a in afscs)
    pilot = client.get("/api/explore/afscs/92T0", headers=admin).json()
    assert pilot["training"] and pilot["alumni"]
    assert client.get("/api/explore/bases/hill", headers=admin).json()["name"] == "Hill AFB, UT"
    assert client.get("/api/explore/bases/nowhere", headers=admin).status_code == 404


def test_serves_built_site_with_client_side_routes(client):
    import main
    if not (main.FRONTEND_DIST / "index.html").is_file():
        return  # dev checkout without a build
    home = client.get("/")
    assert home.status_code == 200 and "<div id=\"root\">" in home.text
    deep = client.get("/alumni")  # a React route must still load the app on refresh
    assert deep.status_code == 200 and "<div id=\"root\">" in deep.text
    csp = deep.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "https://tile.openstreetmap.org " in csp  # map tiles come from this exact host
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/afa-bird.png").headers["content-type"] == "image/png"


def test_migrations_are_current_and_idempotent():
    assert db.schema_version() == len(db.MIGRATIONS)
    db.init_schema()  # running again must be a no-op
    assert db.schema_version() == len(db.MIGRATIONS)

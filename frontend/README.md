# Frontend (React + Vite + TypeScript)

You don't need this folder's tooling to run the app: the pre-built site in `dist/` is served
by the back end. See the root README.

To work on the UI (Node.js 20.19+), start the back end on port 8001, then:

```bash
npm install
npm run dev     # http://localhost:5175, proxies /api to the back end
npm run lint
npm run build   # refresh dist/ before committing
```

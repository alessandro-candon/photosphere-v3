# infra

Cloud Storage and Firebase Storage multi-bucket configuration templates for Photosphere v3.

## Package Boundary & Ownership

- [firebase.json](./firebase.json): Multi-target `storage` mapping (`media` for the Archive bucket and `data` for the Standard bucket), applying the same [storage.rules](./storage.rules) policy to both buckets. Requires the Firebase Blaze pay-as-you-go plan for linking a secondary bucket.
- [storage.rules](./storage.rules): Enforces authenticated `email_verified` and email allowlist checks for reads on both buckets and restricts client writes exclusively to `/photosphere_albums.json`.
- [cors.json](./cors.json): Browser CORS policy applied to both GCS buckets.

## Provisioning Workflow

Run `make init` (or `docker compose run --rm init`) to provision buckets, CORS, empty JSON database seeds, Firebase Storage bucket links, in-memory compiled `storage.rules`, Web App SDK config, and Firebase Auth into root `photosphere.config.json` without modifying tracked files in `infra/`.

For manual reference:

1. Replace `<your-email>` in [storage.rules](./storage.rules) with the authorized user email address(es).
2. Create the Standard-class JSON database bucket if it does not exist yet:
   ```bash
   gcloud storage buckets create gs://<data-bucket> --location=<region> --default-storage-class=STANDARD --uniform-bucket-level-access
   ```
3. Apply CORS to both buckets:
   ```bash
   gcloud storage buckets update gs://<media-bucket> --cors-file=infra/cors.json
   gcloud storage buckets update gs://<data-bucket> --cors-file=infra/cors.json
   ```
4. Link both buckets in Firebase Storage (`firebase target:apply storage media <media-bucket>` and `firebase target:apply storage data <data-bucket>`) and deploy:
   ```bash
   firebase deploy --only storage --config infra/firebase.json
   ```

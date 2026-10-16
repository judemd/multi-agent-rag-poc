# Ephemeral Cloud Run demo

Deployed on 16 October 2026.

| Setting | Value |
|---|---|
| Project | `project-d4ec743e-de8a-4ed5-b45` |
| Region | `us-central1` |
| Service | `beacon-rag-poc` |
| Service URL | https://beacon-rag-poc-13605078295.us-central1.run.app |
| Access | Authenticated Cloud Run IAM access; anonymous requests denied |
| Resources | 1 CPU, 2 GiB memory; minimum 0 / maximum 1 instance |
| Concurrency / request timeout | 10 connections / 3,600 seconds |
| Build identity | `rag-demo-builder@project-d4ec743e-de8a-4ed5-b45.iam.gserviceaccount.com` |
| Runtime identity | `rag-demo-runtime@project-d4ec743e-de8a-4ed5-b45.iam.gserviceaccount.com` |
| Local workflow / vectors | `/tmp/rag-data`, ephemeral SQLite and Chroma |
| Paid AI operations | Disabled (`ENABLE_VERTEX_CALLS=false`) |

## Open in your browser

The service URL is access-restricted; opening it without an identity token returns 403.
Use your authorized Google Cloud CLI login to start a browser-compatible local proxy:

```powershell
gcloud run services proxy beacon-rag-poc --project=project-d4ec743e-de8a-4ed5-b45 --region=us-central1 --port=8080
```

Open http://localhost:8080. This proxies the **hosted** container; it is not your local
Streamlit process. Ctrl+C stops the proxy without deleting the hosted service.
To give another person access, separately authorize an identity/access design. This
deployment does not include public anonymous access or browser Google sign-in through IAP.

Upload or generate data and inspect previews. Agent planning, embedding and chat are
paused initially. No model calls were made as part of deployment verification.

## Enable live AI after authorizing paid use

The runtime has no Vertex role by default. Both the role and the environment opt-in
are needed. These commands grant the dedicated runtime identity Vertex access and deploy
a new revision with billable AI operations enabled:

```powershell
gcloud projects add-iam-policy-binding project-d4ec743e-de8a-4ed5-b45 --member="serviceAccount:rag-demo-runtime@project-d4ec743e-de8a-4ed5-b45.iam.gserviceaccount.com" --role=roles/aiplatform.user --condition=None
gcloud run services update beacon-rag-poc --project=project-d4ec743e-de8a-4ed5-b45 --region=us-central1 --update-env-vars=ENABLE_VERTEX_CALLS=true
```

Updating the service creates a new revision and can discard the current local datasets,
approvals and chat. Decide whether to enable AI before creating a demonstration dataset.
Generation uses `global`; embeddings use `us-central1`. No credentials are baked into
the image: the runtime uses its attached service identity.

## Durability and costs

All original uploads, approvals, sessions, vectors and answers in this deployment can
disappear when an instance is stopped or replaced. Scale-to-zero and session affinity
are not durability guarantees. Local machine data was not uploaded. External Chroma is
not configured; adding only external vectors would still leave workflow state ephemeral.

Cloud Build, Artifact Registry, source storage and Cloud Run can incur charges.
Minimum instances is zero; images and build-source storage remain after the service stops.
The one-instance cap limits scaling but is not a spending cap. Model charges apply when
live AI is enabled and operations are run.

## Build and verification

Cloud Build used the repository Dockerfile because local Docker Desktop was unavailable.
The Linux container build and image push succeeded. Cloud Run revision
`beacon-rag-poc-00001-6gs` became ready. Remote smoke checks verified:

- Anonymous HTTP access: 403.
- Authenticated app page and `/_stcore/health`: 200.
- Authenticated WebSocket connection and a completed Streamlit script render, with no
  rendered application exception.

The build ID is `e6cdef31-f920-4588-a222-cf220ece1cb2`.
The image is stored under
`us-central1-docker.pkg.dev/project-d4ec743e-de8a-4ed5-b45/cloud-run-source-deploy/beacon-rag-poc`.
Source uploads use the project bucket
`run-sources-project-d4ec743e-de8a-4ed5-b45-us-central1`.
`.gcloudignore` excludes local state, credentials and the virtual environment from uploads.

## Redeploy the current source

```powershell
gcloud run deploy beacon-rag-poc --source . --project=project-d4ec743e-de8a-4ed5-b45 --region=us-central1 --build-service-account=projects/project-d4ec743e-de8a-4ed5-b45/serviceAccounts/rag-demo-builder@project-d4ec743e-de8a-4ed5-b45.iam.gserviceaccount.com --service-account=rag-demo-runtime@project-d4ec743e-de8a-4ed5-b45.iam.gserviceaccount.com --port=8080 --memory=2Gi --cpu=1 --max-instances=1 --min-instances=0 --concurrency=10 --timeout=3600 --session-affinity --no-allow-unauthenticated --set-env-vars="GOOGLE_CLOUD_PROJECT=project-d4ec743e-de8a-4ed5-b45,GOOGLE_CLOUD_LOCATION=global,EMBEDDING_LOCATION=us-central1,ENABLE_VERTEX_CALLS=false,DATA_DIR=/tmp/rag-data"
```

This recipe explicitly resets paid AI to disabled. Cloud Run, Cloud Build and Artifact
Registry APIs were already enabled. The dedicated build identity has `roles/run.builder`;
existing project identities and roles were left unchanged.

To remove the hosted service when finished:

```powershell
gcloud run services delete beacon-rag-poc --project=project-d4ec743e-de8a-4ed5-b45 --region=us-central1
```

This does not remove stored container images, uploaded build archives, build history or
the two dedicated service accounts. Review those separately for cleanup; the source bucket
and Artifact Registry repository may contain artifacts from other services.

Official references: [source deployment](https://docs.cloud.google.com/run/docs/deploying-source-code),
[authenticated developer access](https://docs.cloud.google.com/run/docs/authenticating/developers),
and [container filesystem limitations](https://docs.cloud.google.com/run/docs/container-contract).

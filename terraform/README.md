# Terraform: the same platform on AWS EKS

Infrastructure as code for running this platform on EKS instead of kind. **Validated only** (`terraform validate`):
it has not been planned or applied, so treat it as a reviewed draft, not a tested deployment.

## What it creates

| Resource | Replaces in the lab |
|---|---|
| VPC, private and public subnets, one NAT gateway | Docker network |
| EKS cluster with a managed node group on Graviton (arm64) | kind |
| S3 bucket (private, versioned) | MinIO |
| RDS PostgreSQL 17, password generated into Secrets Manager | in-cluster Postgres |
| ECR repositories with immutable tags (a private registry option) | public GHCR images built by `build-images` |
| IAM role bound to the `mlops/mlflow` ServiceAccount via EKS Pod Identity | MinIO root credentials |
| Argo CD plus the root Application (via the `argocd-apps` chart) | `helm install` and `kubectl apply` |

Terraform stops at the cluster boundary: Argo CD deploys everything else from `gitops/apps`.

## Use

```bash
cd terraform
terraform init
terraform plan      # needs AWS credentials
```

## Not done

- `gitops/` still describes the lab. For EKS the MLflow manifests need the S3 bucket, the RDS endpoint and secret, a
  `mlflow` ServiceAccount, and ECR image names; MinIO and Postgres should be dropped. That calls for an EKS overlay.
- Cost was not estimated. The EKS control plane alone is about $73/month, before nodes, the NAT gateway and RDS.
- The API endpoint is public and there is a single NAT gateway; both are marked as shortcuts in the code.

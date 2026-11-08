# --- artifacts: S3 replaces the in-cluster MinIO ---
resource "aws_s3_bucket" "artifacts" {
  bucket_prefix = "${var.name}-mlflow-"
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

# --- metadata: RDS replaces the in-cluster Postgres ---
resource "aws_db_subnet_group" "mlflow" {
  name       = "${var.name}-mlflow"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.name}-rds-"
  vpc_id      = module.vpc.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_nodes" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = module.eks.node_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_db_instance" "mlflow" {
  identifier     = "${var.name}-mlflow"
  engine         = "postgres"
  engine_version = "17"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_encrypted = true

  db_name  = "mlflow"
  username = "mlflow"
  # AWS generates the password and keeps it in Secrets Manager: it never lands in git or in state
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.mlflow.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  # shortcut: no final snapshot and no multi-AZ so `terraform destroy` is clean and cheap; enable both for real data
  skip_final_snapshot = true
  multi_az            = false
}

# --- images: ECR replaces `kind load docker-image` ---
resource "aws_ecr_repository" "images" {
  for_each = toset(["mlops-mlflow", "mlops-train", "mlops-serving"])

  name = each.key
  # immutable tags: the repo pins exact tags (v2, v3), so a tag must never silently change
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- MLflow's access to S3 via EKS Pod Identity (no static keys, unlike the MinIO root credentials in the lab) ---
data "aws_iam_policy_document" "mlflow_s3" {
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.artifacts.arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/*"]
  }
}

resource "aws_iam_policy" "mlflow_s3" {
  name   = "${var.name}-mlflow-s3"
  policy = data.aws_iam_policy_document.mlflow_s3.json
}

data "aws_iam_policy_document" "pod_identity_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "mlflow" {
  name               = "${var.name}-mlflow"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_trust.json
}

resource "aws_iam_role_policy_attachment" "mlflow_s3" {
  role       = aws_iam_role.mlflow.name
  policy_arn = aws_iam_policy.mlflow_s3.arn
}

# binds the role to the `mlflow` ServiceAccount in `mlops` (the manifests must set serviceAccountName: mlflow)
resource "aws_eks_pod_identity_association" "mlflow" {
  cluster_name    = module.eks.cluster_name
  namespace       = "mlops"
  service_account = "mlflow"
  role_arn        = aws_iam_role.mlflow.arn
}

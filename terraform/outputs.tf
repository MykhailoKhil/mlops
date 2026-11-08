output "kubeconfig_command" {
  value = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.region}"
}

output "artifacts_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "mlflow_db_endpoint" {
  value = aws_db_instance.mlflow.address
}

output "mlflow_db_secret_arn" {
  description = "Secrets Manager secret holding the generated RDS master password"
  value       = aws_db_instance.mlflow.master_user_secret[0].secret_arn
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.images : k => r.repository_url }
}

output "mlflow_role_arn" {
  value = aws_iam_role.mlflow.arn
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "name" {
  description = "Prefix for every resource"
  type        = string
  default     = "mlops-lab"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "node_instance_types" {
  description = "Graviton on purpose: the images in this repo are built for arm64"
  type        = list(string)
  default     = ["m7g.large"]
}

variable "gitops_repo_url" {
  description = "Git repo Argo CD syncs from"
  type        = string
  default     = "https://github.com/MykhailoKhil/mlops.git"
}

variable "gitops_path" {
  description = "Directory of Argo CD Applications (app-of-apps)"
  type        = string
  default     = "gitops/apps"
}

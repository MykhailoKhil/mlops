data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name = var.name
  cidr = var.vpc_cidr
  azs  = local.azs

  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, 48 + i)]

  enable_nat_gateway = true
  # shortcut: one NAT gateway saves ~$32/month per extra AZ but is a single point of failure; one per AZ for prod
  single_nat_gateway = true

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name = var.name
  # kubernetes_version left unset: the module then uses the EKS default

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # shortcut: public API endpoint so `terraform apply` and kubectl work from a laptop;
  # restrict with endpoint_public_access_cidrs or go private-only for anything real
  endpoint_public_access                   = true
  enable_cluster_creator_admin_permissions = true

  addons = {
    coredns                = {}
    kube-proxy             = {}
    vpc-cni                = { before_compute = true }
    eks-pod-identity-agent = { before_compute = true }
  }

  eks_managed_node_groups = {
    default = {
      ami_type       = "AL2023_ARM_64_STANDARD"
      instance_types = var.node_instance_types
      min_size       = 1
      max_size       = 3
      desired_size   = 2
    }
  }
}

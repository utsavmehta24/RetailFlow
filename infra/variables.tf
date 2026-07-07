variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "The AWS region to deploy into"
}

variable "raw_bucket_name" {
  type        = string
  default     = "retailflow-raw"
  description = "The name of the raw S3 bucket"
}

variable "curated_bucket_name" {
  type        = string
  default     = "retailflow-curated"
  description = "The name of the curated S3 bucket"
}

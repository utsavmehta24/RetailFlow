output "raw_bucket_name" {
  value       = aws_s3_bucket.raw.id
  description = "The name of the raw S3 bucket"
}

output "curated_bucket_name" {
  value       = aws_s3_bucket.curated.id
  description = "The name of the curated S3 bucket"
}

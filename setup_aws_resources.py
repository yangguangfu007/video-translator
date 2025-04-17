import boto3
import json
import argparse
import os
from dotenv import load_dotenv

def create_s3_bucket(region, bucket_name):
    """Create an S3 bucket for storing video files and outputs."""
    s3_client = boto3.client('s3', region_name=region)
    
    try:
        if region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
            )
        print(f"Created S3 bucket: {bucket_name}")
        
        # Set bucket policy to allow MediaConvert access
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "mediaconvert.amazonaws.com"},
                    "Action": ["s3:GetObject", "s3:PutObject"],
                    "Resource": f"arn:aws:s3:::{bucket_name}/*"
                }
            ]
        }
        s3_client.put_bucket_policy(
            Bucket=bucket_name,
            Policy=json.dumps(bucket_policy)
        )
        print(f"Set bucket policy for MediaConvert access")
        
        return True
    except Exception as e:
        if "BucketAlreadyOwnedByYou" in str(e):
            print(f"Bucket {bucket_name} already exists and is owned by you.")
            return True
        else:
            print(f"Error creating S3 bucket: {str(e)}")
            return False

def create_mediaconvert_role(role_name):
    """Create an IAM role for MediaConvert with necessary permissions."""
    iam_client = boto3.client('iam')
    
    try:
        # Create the role
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "mediaconvert.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="Role for AWS MediaConvert service"
        )
        
        role_arn = response['Role']['Arn']
        print(f"Created IAM role: {role_name} with ARN: {role_arn}")
        
        # Attach necessary policies
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess"
        )
        print("Attached S3 access policy to the role")
        
        return role_arn
    except Exception as e:
        if "EntityAlreadyExists" in str(e):
            print(f"Role {role_name} already exists.")
            role = iam_client.get_role(RoleName=role_name)
            return role['Role']['Arn']
        else:
            print(f"Error creating IAM role: {str(e)}")
            return None

def main():
    parser = argparse.ArgumentParser(description="Set up AWS resources for the video translator application")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--bucket-name", required=True, help="S3 bucket name")
    parser.add_argument("--role-name", default="VideoTranslatorMediaConvertRole", help="IAM role name for MediaConvert")
    args = parser.parse_args()
    
    # Create S3 bucket
    bucket_created = create_s3_bucket(args.region, args.bucket_name)
    if not bucket_created:
        print("Failed to create S3 bucket. Exiting.")
        return
    
    # Create MediaConvert role
    role_arn = create_mediaconvert_role(args.role_name)
    if not role_arn:
        print("Failed to create MediaConvert role. Exiting.")
        return
    
    # Create or update .env file
    env_file = ".env"
    if os.path.exists(env_file):
        load_dotenv(env_file)
    
    with open(env_file, "w") as f:
        f.write(f"AWS_REGION={args.region}\n")
        f.write(f"S3_BUCKET_NAME={args.bucket_name}\n")
        f.write(f"MEDIACONVERT_ROLE_ARN={role_arn}\n")
        
        # Preserve existing values if they exist
        for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "BEDROCK_MODEL_ID"]:
            if os.getenv(key):
                f.write(f"{key}={os.getenv(key)}\n")
    
    print(f"Updated .env file with AWS resource information")
    print("\nSetup complete! You can now run the video translator application.")
    print("Make sure to add your AWS credentials to the .env file if they're not already set.")

if __name__ == "__main__":
    main()

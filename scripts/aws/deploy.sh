#!/usr/bin/env bash

set -euo pipefail

export AWS_PAGER=""

AWS_REGION="${AWS_REGION:-us-west-2}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
APP_NAME="${APP_NAME:-recraft-web-demo}"
ECR_REPOSITORY="${ECR_REPOSITORY:-$APP_NAME}"
EC2_INSTANCE_ROLE_NAME="${EC2_INSTANCE_ROLE_NAME:-RecraftEc2InstanceRole}"
EC2_INSTANCE_PROFILE_NAME="${EC2_INSTANCE_PROFILE_NAME:-RecraftEc2InstanceProfile}"
EC2_SECURITY_GROUP_NAME="${EC2_SECURITY_GROUP_NAME:-RecraftWebDemoSg}"
EC2_INSTANCE_NAME="${EC2_INSTANCE_NAME:-recraft-web-demo}"
EC2_EIP_NAME="${EC2_EIP_NAME:-recraft-web-demo-eip}"
SSM_PREFIX="${SSM_PREFIX:-/recraft/prod}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.small}"
AMI_SSM_PARAMETER="${AMI_SSM_PARAMETER:-/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPOSITORY_URI="${ECR_REGISTRY}/${ECR_REPOSITORY}"
IMAGE_URI="${ECR_REPOSITORY_URI}:${IMAGE_TAG}"

temp_dir="$(mktemp -d)"
trap 'rm -rf "${temp_dir}"' EXIT

user_data_path="${temp_dir}/user-data.sh"

ensure_instance_role() {
  local trust_policy_path="${temp_dir}/ec2-trust.json"
  local ssm_policy_path="${temp_dir}/ec2-ssm-policy.json"

  jq -n '{
    Version: "2012-10-17",
    Statement: [
      {
        Effect: "Allow",
        Principal: { Service: "ec2.amazonaws.com" },
        Action: "sts:AssumeRole"
      }
    ]
  }' > "${trust_policy_path}"

  jq -n \
    --arg aws_region "${AWS_REGION}" \
    --arg aws_account_id "${AWS_ACCOUNT_ID}" \
    --arg ssm_prefix "${SSM_PREFIX}" '
  {
    Version: "2012-10-17",
    Statement: [
      {
        Effect: "Allow",
        Action: [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ],
        Resource: [
          ("arn:aws:ssm:" + $aws_region + ":" + $aws_account_id + ":parameter" + $ssm_prefix + "/GEMINI_API_KEY"),
          ("arn:aws:ssm:" + $aws_region + ":" + $aws_account_id + ":parameter" + $ssm_prefix + "/ANALYSIS_MODEL"),
          ("arn:aws:ssm:" + $aws_region + ":" + $aws_account_id + ":parameter" + $ssm_prefix + "/SEARCH_MODEL"),
          ("arn:aws:ssm:" + $aws_region + ":" + $aws_account_id + ":parameter" + $ssm_prefix + "/IMAGE_MODEL"),
          ("arn:aws:ssm:" + $aws_region + ":" + $aws_account_id + ":parameter" + $ssm_prefix + "/MOCK_FALLBACK_ENABLED")
        ]
      },
      {
        Effect: "Allow",
        Action: [
          "kms:Decrypt"
        ],
        Resource: "*"
      }
    ]
  }' > "${ssm_policy_path}"

  if ! aws iam get-role --role-name "${EC2_INSTANCE_ROLE_NAME}" >/dev/null 2>&1; then
    aws iam create-role \
      --role-name "${EC2_INSTANCE_ROLE_NAME}" \
      --assume-role-policy-document "file://${trust_policy_path}" >/dev/null
  fi

  aws iam attach-role-policy \
    --role-name "${EC2_INSTANCE_ROLE_NAME}" \
    --policy-arn "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly" >/dev/null

  aws iam attach-role-policy \
    --role-name "${EC2_INSTANCE_ROLE_NAME}" \
    --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" >/dev/null

  aws iam put-role-policy \
    --role-name "${EC2_INSTANCE_ROLE_NAME}" \
    --policy-name "RecraftEc2SsmReadPolicy" \
    --policy-document "file://${ssm_policy_path}" >/dev/null

  if ! aws iam get-instance-profile --instance-profile-name "${EC2_INSTANCE_PROFILE_NAME}" >/dev/null 2>&1; then
    aws iam create-instance-profile --instance-profile-name "${EC2_INSTANCE_PROFILE_NAME}" >/dev/null
    sleep 5
  fi

  if ! aws iam get-instance-profile \
    --instance-profile-name "${EC2_INSTANCE_PROFILE_NAME}" \
    --query "InstanceProfile.Roles[?RoleName=='${EC2_INSTANCE_ROLE_NAME}'] | length(@)" \
    --output text | grep -qx '1'; then
    aws iam add-role-to-instance-profile \
      --instance-profile-name "${EC2_INSTANCE_PROFILE_NAME}" \
      --role-name "${EC2_INSTANCE_ROLE_NAME}" >/dev/null || true
    sleep 10
  fi
}

ensure_security_group() {
  local vpc_id
  vpc_id="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --region "${AWS_REGION}" --query 'Vpcs[0].VpcId' --output text)"

  if [[ "${vpc_id}" == "None" || -z "${vpc_id}" ]]; then
    echo "No default VPC found in ${AWS_REGION}." >&2
    exit 1
  fi

  local security_group_id
  security_group_id="$(aws ec2 describe-security-groups \
    --region "${AWS_REGION}" \
    --filters Name=group-name,Values="${EC2_SECURITY_GROUP_NAME}" Name=vpc-id,Values="${vpc_id}" \
    --query 'SecurityGroups[0].GroupId' \
    --output text)"

  if [[ "${security_group_id}" == "None" || -z "${security_group_id}" ]]; then
    security_group_id="$(aws ec2 create-security-group \
      --region "${AWS_REGION}" \
      --group-name "${EC2_SECURITY_GROUP_NAME}" \
      --description "Public HTTP access for ${APP_NAME}" \
      --vpc-id "${vpc_id}" \
      --query 'GroupId' \
      --output text)"

    aws ec2 create-tags \
      --region "${AWS_REGION}" \
      --resources "${security_group_id}" \
      --tags Key=Name,Value="${EC2_SECURITY_GROUP_NAME}" Key=Service,Value="${APP_NAME}" >/dev/null
  fi

  aws ec2 authorize-security-group-ingress \
    --region "${AWS_REGION}" \
    --group-id "${security_group_id}" \
    --ip-permissions '[
      {"IpProtocol":"tcp","FromPort":80,"ToPort":80,"IpRanges":[{"CidrIp":"0.0.0.0/0","Description":"HTTP"}]},
      {"IpProtocol":"tcp","FromPort":443,"ToPort":443,"IpRanges":[{"CidrIp":"0.0.0.0/0","Description":"HTTPS passthrough placeholder"}]}
    ]' >/dev/null 2>&1 || true

  printf '%s' "${security_group_id}"
}

ensure_eip() {
  local allocation_id
  allocation_id="$(aws ec2 describe-addresses \
    --region "${AWS_REGION}" \
    --filters Name=tag:Name,Values="${EC2_EIP_NAME}" \
    --query 'Addresses[0].AllocationId' \
    --output text)"

  if [[ "${allocation_id}" == "None" || -z "${allocation_id}" ]]; then
    allocation_id="$(aws ec2 allocate-address --region "${AWS_REGION}" --domain vpc --query 'AllocationId' --output text)"
    aws ec2 create-tags \
      --region "${AWS_REGION}" \
      --resources "${allocation_id}" \
      --tags Key=Name,Value="${EC2_EIP_NAME}" Key=Service,Value="${APP_NAME}" >/dev/null
  fi

  printf '%s' "${allocation_id}"
}

build_and_push_image() {
  aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

  docker build \
    --file api/Dockerfile \
    --build-arg VITE_API_BASE_URL="/" \
    --tag "${IMAGE_URI}" \
    .

  docker push "${IMAGE_URI}"
}

write_user_data() {
cat > "${user_data_path}" <<EOF
#!/bin/bash
set -euxo pipefail

dnf install -y docker jq awscli
systemctl enable --now docker

aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

GEMINI_API_KEY=\$(aws ssm get-parameter --region "${AWS_REGION}" --name "${SSM_PREFIX}/GEMINI_API_KEY" --with-decryption --query 'Parameter.Value' --output text)
ANALYSIS_MODEL=\$(aws ssm get-parameter --region "${AWS_REGION}" --name "${SSM_PREFIX}/ANALYSIS_MODEL" --query 'Parameter.Value' --output text)
SEARCH_MODEL=\$(aws ssm get-parameter --region "${AWS_REGION}" --name "${SSM_PREFIX}/SEARCH_MODEL" --query 'Parameter.Value' --output text)
IMAGE_MODEL=\$(aws ssm get-parameter --region "${AWS_REGION}" --name "${SSM_PREFIX}/IMAGE_MODEL" --query 'Parameter.Value' --output text)
MOCK_FALLBACK_ENABLED=\$(aws ssm get-parameter --region "${AWS_REGION}" --name "${SSM_PREFIX}/MOCK_FALLBACK_ENABLED" --query 'Parameter.Value' --output text)

docker pull "${IMAGE_URI}"
docker rm -f "${APP_NAME}" || true
docker run -d \
  --name "${APP_NAME}" \
  --restart unless-stopped \
  -p 80:8000 \
  -e GEMINI_API_KEY="\${GEMINI_API_KEY}" \
  -e ANALYSIS_MODEL="\${ANALYSIS_MODEL}" \
  -e SEARCH_MODEL="\${SEARCH_MODEL}" \
  -e IMAGE_MODEL="\${IMAGE_MODEL}" \
  -e MOCK_FALLBACK_ENABLED="\${MOCK_FALLBACK_ENABLED}" \
  "${IMAGE_URI}"
EOF
}

launch_instance() {
  local security_group_id="$1"
  local ami_id
  local subnet_id

  ami_id="$(aws ssm get-parameter --region "${AWS_REGION}" --name "${AMI_SSM_PARAMETER}" --query 'Parameter.Value' --output text)"
  subnet_id="$(aws ec2 describe-subnets --region "${AWS_REGION}" --filters Name=default-for-az,Values=true --query 'Subnets[0].SubnetId' --output text)"

  if [[ "${subnet_id}" == "None" || -z "${subnet_id}" ]]; then
    echo "No default subnet found in ${AWS_REGION}." >&2
    exit 1
  fi

  aws ec2 run-instances \
    --region "${AWS_REGION}" \
    --image-id "${ami_id}" \
    --instance-type "${INSTANCE_TYPE}" \
    --iam-instance-profile Name="${EC2_INSTANCE_PROFILE_NAME}" \
    --security-group-ids "${security_group_id}" \
    --subnet-id "${subnet_id}" \
    --associate-public-ip-address \
    --metadata-options 'HttpTokens=required,HttpEndpoint=enabled' \
    --user-data "file://${user_data_path}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${EC2_INSTANCE_NAME}},{Key=Service,Value=${APP_NAME}},{Key=ImageTag,Value=${IMAGE_TAG}}]" "ResourceType=volume,Tags=[{Key=Name,Value=${EC2_INSTANCE_NAME}},{Key=Service,Value=${APP_NAME}}]" \
    --query 'Instances[0].InstanceId' \
    --output text
}

wait_for_app() {
  local public_ip="$1"

  for _ in $(seq 1 90); do
    if curl --fail --silent --show-error --max-time 10 "http://${public_ip}/health" >/dev/null; then
      return 0
    fi
    sleep 10
  done

  return 1
}

build_and_push_image
ensure_instance_role
security_group_id="$(ensure_security_group)"
allocation_id="$(ensure_eip)"
write_user_data

existing_instance_ids="$(aws ec2 describe-instances \
  --region "${AWS_REGION}" \
  --filters Name=tag:Service,Values="${APP_NAME}" Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[].Instances[].InstanceId' \
  --output text)"

new_instance_id="$(launch_instance "${security_group_id}")"

aws ec2 wait instance-running --region "${AWS_REGION}" --instance-ids "${new_instance_id}"
aws ec2 wait instance-status-ok --region "${AWS_REGION}" --instance-ids "${new_instance_id}"

new_public_ip="$(aws ec2 describe-instances \
  --region "${AWS_REGION}" \
  --instance-ids "${new_instance_id}" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)"

echo "Waiting for application health on ${new_public_ip}..."
if ! wait_for_app "${new_public_ip}"; then
  echo "Application failed to become healthy on the new instance." >&2
  exit 1
fi

aws ec2 associate-address \
  --region "${AWS_REGION}" \
  --allocation-id "${allocation_id}" \
  --instance-id "${new_instance_id}" \
  --allow-reassociation >/dev/null

public_eip="$(aws ec2 describe-addresses \
  --region "${AWS_REGION}" \
  --allocation-ids "${allocation_id}" \
  --query 'Addresses[0].PublicIp' \
  --output text)"

if [[ -n "${existing_instance_ids}" && "${existing_instance_ids}" != "None" ]]; then
  old_instance_ids=""
  for instance_id in ${existing_instance_ids}; do
    if [[ "${instance_id}" != "${new_instance_id}" ]]; then
      old_instance_ids+=" ${instance_id}"
    fi
  done

  if [[ -n "${old_instance_ids// }" ]]; then
    aws ec2 terminate-instances --region "${AWS_REGION}" --instance-ids ${old_instance_ids} >/dev/null
  fi
fi

echo "Deployment complete."
echo "EC2 instance: ${new_instance_id}"
echo "Public URL: http://${public_eip}/"

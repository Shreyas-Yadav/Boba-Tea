#!/usr/bin/env bash

set -euo pipefail

export AWS_PAGER=""

AWS_REGION="${AWS_REGION:-us-west-2}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
APP_NAME="${APP_NAME:-recraft-web-demo}"
ECR_REPOSITORY="${ECR_REPOSITORY:-$APP_NAME}"
EC2_INSTANCE_ROLE_NAME="${EC2_INSTANCE_ROLE_NAME:-RecraftEc2InstanceRole}"
EC2_INSTANCE_PROFILE_NAME="${EC2_INSTANCE_PROFILE_NAME:-RecraftEc2InstanceProfile}"
GITHUB_DEPLOY_ROLE_NAME="${GITHUB_DEPLOY_ROLE_NAME:-GitHubActionsRecraftDeployRole}"
REPO_SLUG="${REPO_SLUG:-Shreyas-Yadav/Boba-Tea}"
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"
SSM_PREFIX="${SSM_PREFIX:-/recraft/prod}"

GEMINI_API_KEY="${GEMINI_API_KEY:-}"
ANALYSIS_MODEL="${ANALYSIS_MODEL:-gemini-3-flash-preview}"
SEARCH_MODEL="${SEARCH_MODEL:-gemini-3-flash-preview}"
IMAGE_MODEL="${IMAGE_MODEL:-gemini-3.1-flash-image-preview}"
MOCK_FALLBACK_ENABLED="${MOCK_FALLBACK_ENABLED:-false}"

if [[ -z "${GEMINI_API_KEY}" ]]; then
  echo "GEMINI_API_KEY must be set before running bootstrap." >&2
  exit 1
fi

temp_dir="$(mktemp -d)"
trap 'rm -rf "${temp_dir}"' EXIT

ec2_trust_policy="${temp_dir}/ec2-trust.json"
ec2_ssm_policy="${temp_dir}/ec2-ssm-policy.json"
github_trust_policy="${temp_dir}/github-oidc-trust.json"
github_permissions_policy="${temp_dir}/github-deploy-policy.json"

jq -n '{
  Version: "2012-10-17",
  Statement: [
    {
      Effect: "Allow",
      Principal: { Service: "ec2.amazonaws.com" },
      Action: "sts:AssumeRole"
    }
  ]
}' > "${ec2_trust_policy}"

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
}' > "${ec2_ssm_policy}"

oidc_provider_arn="arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

if ! aws iam get-open-id-connect-provider --open-id-connect-provider-arn "${oidc_provider_arn}" >/dev/null 2>&1; then
  aws iam create-open-id-connect-provider \
    --url "https://token.actions.githubusercontent.com" \
    --client-id-list "sts.amazonaws.com" \
    --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1" >/dev/null
fi

jq -n \
  --arg aws_account_id "${AWS_ACCOUNT_ID}" \
  --arg repo_slug "${REPO_SLUG}" \
  --arg branch_ref "refs/heads/${GITHUB_BRANCH}" '
{
  Version: "2012-10-17",
  Statement: [
    {
      Effect: "Allow",
      Principal: {
        Federated: ("arn:aws:iam::" + $aws_account_id + ":oidc-provider/token.actions.githubusercontent.com")
      },
      Action: "sts:AssumeRoleWithWebIdentity",
      Condition: {
        StringEquals: {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": ("repo:" + $repo_slug + ":ref:" + $branch_ref)
        }
      }
    }
  ]
}' > "${github_trust_policy}"

jq -n \
  --arg aws_region "${AWS_REGION}" \
  --arg aws_account_id "${AWS_ACCOUNT_ID}" \
  --arg ecr_repository "${ECR_REPOSITORY}" \
  --arg ec2_instance_role_name "${EC2_INSTANCE_ROLE_NAME}" \
  --arg ec2_instance_profile_name "${EC2_INSTANCE_PROFILE_NAME}" '
{
  Version: "2012-10-17",
  Statement: [
    {
      Effect: "Allow",
      Action: [
        "ecr:GetAuthorizationToken"
      ],
      Resource: "*"
    },
    {
      Effect: "Allow",
      Action: [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchDeleteImage",
        "ecr:CompleteLayerUpload",
        "ecr:CreateRepository",
        "ecr:DescribeImages",
        "ecr:DescribeRepositories",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      Resource: [
        ("arn:aws:ecr:" + $aws_region + ":" + $aws_account_id + ":repository/" + $ecr_repository)
      ]
    },
    {
      Effect: "Allow",
      Action: [
        "ec2:AllocateAddress",
        "ec2:AssociateAddress",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:CreateSecurityGroup",
        "ec2:CreateTags",
        "ec2:DescribeAddresses",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeVpcs",
        "ec2:RunInstances",
        "ec2:TerminateInstances"
      ],
      Resource: "*"
    },
    {
      Effect: "Allow",
      Action: [
        "iam:AddRoleToInstanceProfile",
        "iam:AttachRolePolicy",
        "iam:CreateInstanceProfile",
        "iam:CreateRole",
        "iam:GetInstanceProfile",
        "iam:GetRole",
        "iam:PassRole",
        "iam:PutRolePolicy"
      ],
      Resource: [
        ("arn:aws:iam::" + $aws_account_id + ":role/" + $ec2_instance_role_name),
        ("arn:aws:iam::" + $aws_account_id + ":instance-profile/" + $ec2_instance_profile_name)
      ]
    },
    {
      Effect: "Allow",
      Action: [
        "ssm:GetParameter"
      ],
      Resource: ("arn:aws:ssm:" + $aws_region + "::parameter/aws/service/ami-amazon-linux-latest/*")
    }
  ]
}' > "${github_permissions_policy}"

if ! aws ecr describe-repositories --repository-names "${ECR_REPOSITORY}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  aws ecr create-repository --repository-name "${ECR_REPOSITORY}" --region "${AWS_REGION}" >/dev/null
fi

if ! aws iam get-role --role-name "${EC2_INSTANCE_ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role \
    --role-name "${EC2_INSTANCE_ROLE_NAME}" \
    --assume-role-policy-document "file://${ec2_trust_policy}" >/dev/null
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
  --policy-document "file://${ec2_ssm_policy}" >/dev/null

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

if ! aws iam get-role --role-name "${GITHUB_DEPLOY_ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role \
    --role-name "${GITHUB_DEPLOY_ROLE_NAME}" \
    --assume-role-policy-document "file://${github_trust_policy}" >/dev/null
fi

aws iam put-role-policy \
  --role-name "${GITHUB_DEPLOY_ROLE_NAME}" \
  --policy-name "RecraftGitHubDeployPolicy" \
  --policy-document "file://${github_permissions_policy}" >/dev/null

aws ssm put-parameter \
  --name "${SSM_PREFIX}/GEMINI_API_KEY" \
  --type "SecureString" \
  --value "${GEMINI_API_KEY}" \
  --overwrite \
  --region "${AWS_REGION}" >/dev/null

aws ssm put-parameter \
  --name "${SSM_PREFIX}/ANALYSIS_MODEL" \
  --type "String" \
  --value "${ANALYSIS_MODEL}" \
  --overwrite \
  --region "${AWS_REGION}" >/dev/null

aws ssm put-parameter \
  --name "${SSM_PREFIX}/SEARCH_MODEL" \
  --type "String" \
  --value "${SEARCH_MODEL}" \
  --overwrite \
  --region "${AWS_REGION}" >/dev/null

aws ssm put-parameter \
  --name "${SSM_PREFIX}/IMAGE_MODEL" \
  --type "String" \
  --value "${IMAGE_MODEL}" \
  --overwrite \
  --region "${AWS_REGION}" >/dev/null

aws ssm put-parameter \
  --name "${SSM_PREFIX}/MOCK_FALLBACK_ENABLED" \
  --type "String" \
  --value "${MOCK_FALLBACK_ENABLED}" \
  --overwrite \
  --region "${AWS_REGION}" >/dev/null

echo "Bootstrap complete."
echo "ECR repository: ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"
echo "EC2 instance role: arn:aws:iam::${AWS_ACCOUNT_ID}:role/${EC2_INSTANCE_ROLE_NAME}"
echo "EC2 instance profile: arn:aws:iam::${AWS_ACCOUNT_ID}:instance-profile/${EC2_INSTANCE_PROFILE_NAME}"
echo "GitHub OIDC deploy role: arn:aws:iam::${AWS_ACCOUNT_ID}:role/${GITHUB_DEPLOY_ROLE_NAME}"

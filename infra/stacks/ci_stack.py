import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

DEPLOY_ROLE_NAME = "warszawa-live-github-deploy"


class CiStack(cdk.Stack):
    """Lets GitHub Actions on the master branch deploy via OIDC (no stored AWS keys)."""

    def __init__(
        self, scope: Construct, id: str, *, github_repo: str, migrate_function: lambda_.IFunction, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        provider = iam.CfnOIDCProvider(
            self,
            "GitHubOidc",
            url="https://token.actions.githubusercontent.com",
            client_id_list=["sts.amazonaws.com"],
        )

        role = iam.Role(
            self,
            "DeployRole",
            role_name=DEPLOY_ROLE_NAME,
            max_session_duration=cdk.Duration.hours(1),
            assumed_by=iam.WebIdentityPrincipal(
                provider.attr_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        "token.actions.githubusercontent.com:sub": f"repo:{github_repo}:ref:refs/heads/master",
                    }
                },
            ),
        )
        # cdk deploy works by assuming the bootstrap roles; it needs nothing else
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[f"arn:aws:iam::{self.account}:role/cdk-hnb659fds-*-{self.account}-{self.region}"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudformation:DescribeStacks"],
                resources=[f"arn:aws:cloudformation:{self.region}:{self.account}:stack/WarszawaLive*/*"],
            )
        )
        migrate_function.grant_invoke(role)

        cdk.CfnOutput(self, "DeployRoleArn", value=role.role_arn)

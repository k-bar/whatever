import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

from stacks.db_stack import DbStack

# People who need a DB client (DataGrip etc.) on the dev schema. Access path: SSM port-forward
# through the dev box (no SSH, DB not exposed). Postgres role is created by deploy/db-user.sql.
DEV_DB_USERS = ["kamil"]


class TeamStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, db: DbStack, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        for name in DEV_DB_USERS:
            secret = sm.Secret(
                self,
                f"{name.capitalize()}DbLogin",
                secret_name=f"warszawa-live/dev/db-users/{name}",
                generate_secret_string=sm.SecretStringGenerator(
                    secret_string_template=f'{{"username": "{name}", "dbname": "warszawa", "schema": "dev"}}',
                    generate_string_key="password",
                    password_length=32,
                    exclude_punctuation=True,
                ),
            )
            user = iam.User(self, f"{name.capitalize()}User", user_name=f"warszawa-{name}")
            secret.grant_read(user)
            # Tunnel to the dev box only (matched by tag, so box replacements keep working)
            user.add_to_policy(
                iam.PolicyStatement(
                    actions=["ssm:StartSession"],
                    resources=[f"arn:aws:ec2:{self.region}:{self.account}:instance/*"],
                    conditions={"StringEquals": {"ssm:resourceTag/env": "dev"}},
                )
            )
            user.add_to_policy(
                iam.PolicyStatement(
                    actions=["ssm:StartSession"],
                    resources=[f"arn:aws:ssm:{self.region}::document/AWS-StartPortForwardingSessionToRemoteHost"],
                )
            )
            user.add_to_policy(
                iam.PolicyStatement(
                    actions=["ssm:TerminateSession", "ssm:ResumeSession"],
                    resources=[f"arn:aws:ssm:*:{self.account}:session/${{aws:username}}-*"],
                )
            )
            user.add_to_policy(
                iam.PolicyStatement(actions=["ec2:DescribeInstances", "cloudformation:DescribeStacks"], resources=["*"])
            )
            cdk.CfnOutput(self, f"{name.capitalize()}SecretArn", value=secret.secret_arn)

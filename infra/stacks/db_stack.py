import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

DB_NAME = "warszawa"


class DbStack(cdk.Stack):
    """Shared by both environments: one RDS instance (prod = schema public, dev = schema dev),
    the security group of the app boxes, and secrets.

    Postgres only accepts the app boxes (plus the internet while `db_open_to_internet` is true in
    cdk.json, kept during the Lambda -> EC2 move). SSL is forced; the password is generated.
    """

    def __init__(self, scope: Construct, id: str, *, open_to_internet: bool, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.vpc = vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        # App boxes: HTTP only from CloudFront's origin-facing IP ranges; no SSH (use SSM Session Manager)
        self.app_sg = ec2.SecurityGroup(
            self, "AppSg", vpc=vpc, description="Warszawa Live app boxes (HTTP from CloudFront only)"
        )
        cloudfront_ips = ec2.PrefixList.from_lookup(
            self, "CloudFrontOrigins", prefix_list_name="com.amazonaws.global.cloudfront.origin-facing"
        )
        self.app_sg.add_ingress_rule(
            ec2.Peer.prefix_list(cloudfront_ips.prefix_list_id), ec2.Port.tcp(80), "CloudFront to API"
        )

        sg = ec2.SecurityGroup(self, "DbSg", vpc=vpc, description="Postgres for Warszawa Live (SSL only)")
        sg.add_ingress_rule(self.app_sg, ec2.Port.tcp(5432), "app boxes")
        if open_to_internet:
            sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5432), "temporary: Lambda / migration")

        params = rds.ParameterGroup(
            self,
            "DbParams",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.of("16", "16")),
            parameters={"rds.force_ssl": "1"},
        )

        self.instance = rds.DatabaseInstance(
            self,
            "Postgres",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.of("16", "16")),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE4_GRAVITON, ec2.InstanceSize.MICRO),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            publicly_accessible=True,
            security_groups=[sg],
            parameter_group=params,
            database_name=DB_NAME,
            credentials=rds.Credentials.from_generated_secret(
                "warszawa", secret_name="warszawa-live/db", exclude_characters=" %+~`#$&*()|[]{}:;<>?!'/@\"\\"
            ),
            allocated_storage=20,
            max_allocated_storage=50,
            storage_type=rds.StorageType.GP3,
            storage_encrypted=True,
            backup_retention=cdk.Duration.days(1),
            multi_az=False,
            auto_minor_version_upgrade=True,
            deletion_protection=True,
            removal_policy=cdk.RemovalPolicy.SNAPSHOT,
        )
        self.db_secret = self.instance.secret

        self.jwt_secret = sm.Secret(
            self,
            "JwtSecret",
            secret_name="warszawa-live/jwt",
            generate_secret_string=sm.SecretStringGenerator(password_length=64, exclude_punctuation=True),
        )
        # Value set by hand: aws secretsmanager put-secret-value --secret-id warszawa-live/warsaw-api-token ...
        self.warsaw_token = sm.Secret(
            self,
            "WarsawApiToken",
            secret_name="warszawa-live/warsaw-api-token",
            secret_string_value=cdk.SecretValue.unsafe_plain_text("CHANGE_ME"),
        )

        # Read-only GitHub deploy key (private half) used by the app boxes to pull the repo.
        # Value set by hand; the public half is added by the repo owner under Settings -> Deploy keys.
        self.deploy_key = sm.Secret(
            self,
            "DeployKey",
            secret_name="warszawa-live/deploy-key",
            secret_string_value=cdk.SecretValue.unsafe_plain_text("CHANGE_ME"),
        )

        cdk.CfnOutput(self, "DbEndpoint", value=self.instance.db_instance_endpoint_address)
        cdk.CfnOutput(self, "DbSecretName", value="warszawa-live/db")

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

DB_NAME = "warszawa"


class DbStack(cdk.Stack):
    """Postgres reachable from the internet (Lambdas run outside a VPC, so no NAT bill).

    Protection = SSL-only connections + a 32-char generated password in Secrets Manager.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        sg = ec2.SecurityGroup(self, "DbSg", vpc=vpc, description="Postgres for Warszawa Live (SSL only)")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5432), "Lambda / dev access, password + SSL")
        # Synth warns (W2508, W9011) about the open port and public instance: accepted, see class docstring.

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

        cdk.CfnOutput(self, "DbEndpoint", value=self.instance.db_instance_endpoint_address)
        cdk.CfnOutput(self, "DbSecretName", value="warszawa-live/db")

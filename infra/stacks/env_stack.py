from dataclasses import dataclass
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as r53_targets
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct

from stacks.db_stack import DbStack
from stacks.dns_stack import DnsStack

EC2_DIR = Path(__file__).resolve().parent.parent / "ec2"
GIT_REPO = "git@github.com:k-bar/whatever.git"


@dataclass(frozen=True)
class EnvConfig:
    name: str  # "prod" / "dev"
    release_branch: str  # moved by .github/workflows/release.yml after CI passes
    db_schema: str  # "" = public
    ingest_schedule: str  # systemd OnCalendar
    geocode_limit: int
    web_hosts: tuple[str, ...]  # subdomains for the site; "" = apex
    api_host: str  # subdomain for the API


class EnvStack(cdk.Stack):
    """One environment: EC2 box (API + ingest + deploy agent), API CloudFront, website bucket + CloudFront."""

    def __init__(
        self, scope: Construct, id: str, *, cfg: EnvConfig, db: DbStack, dns: DnsStack | None = None, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        def fqdn(sub: str) -> str:
            return f"{sub}.{dns.domain}" if sub else dns.domain

        # --- secrets --------------------------------------------------------------------------
        jwt = (
            db.jwt_secret
            if cfg.name == "prod"
            else sm.Secret(
                self,
                "JwtSecret",
                secret_name=f"warszawa-live/{cfg.name}/jwt",
                generate_secret_string=sm.SecretStringGenerator(password_length=64, exclude_punctuation=True),
            )
        )

        # --- box ------------------------------------------------------------------------------
        eip = ec2.CfnEIP(self, "Ip", domain="vpc", tags=[cdk.CfnTag(key="Name", value=f"warszawa-{cfg.name}")])
        # CloudFront needs a hostname, not an IP: EC2's public DNS name for the Elastic IP
        origin_host = cdk.Fn.join(
            "",
            ["ec2-", cdk.Fn.join("-", cdk.Fn.split(".", eip.attr_public_ip)), f".{self.region}.compute.amazonaws.com"],
        )

        # --- API CloudFront -------------------------------------------------------------------
        api_cdn = cloudfront.Distribution(
            self,
            "ApiCdn",
            comment=f"warszawa-live {cfg.name} API",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.HttpOrigin(origin_host, protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
            ),
            domain_names=[fqdn(cfg.api_host)] if dns else None,
            certificate=dns.certificate if dns else None,
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )
        api_url = f"https://{fqdn(cfg.api_host)}" if dns else f"https://{api_cdn.distribution_domain_name}"

        # --- website --------------------------------------------------------------------------
        bucket = s3.Bucket(
            self,
            "Site",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        web_cdn = cloudfront.Distribution(
            self,
            "WebCdn",
            comment=f"warszawa-live {cfg.name} website",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            # SPA: unknown paths serve index.html and the router handles them
            error_responses=[
                cloudfront.ErrorResponse(http_status=s, response_http_status=200, response_page_path="/index.html")
                for s in (403, 404)
            ],
            domain_names=[fqdn(h) for h in cfg.web_hosts] if dns else None,
            certificate=dns.certificate if dns else None,
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )
        web_url = f"https://{fqdn(cfg.web_hosts[0])}" if dns else f"https://{web_cdn.distribution_domain_name}"

        if dns:
            for host, dist in [(cfg.api_host, api_cdn), *[(h, web_cdn) for h in cfg.web_hosts]]:
                target = route53.RecordTarget.from_alias(r53_targets.CloudFrontTarget(dist))
                rid = host.replace("-", "") or "apex"
                route53.ARecord(self, f"A{rid}", zone=dns.zone, record_name=host or None, target=target)
                route53.AaaaRecord(self, f"Aaaa{rid}", zone=dns.zone, record_name=host or None, target=target)

        # --- box permissions ------------------------------------------------------------------
        self.role = role = iam.Role(
            self,
            "BoxRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")],
        )
        for secret in (db.db_secret, jwt, db.warsaw_token, db.deploy_key):
            secret.grant_read(role)
        bucket.grant_read_write(role)
        bucket.grant_delete(role)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudfront:CreateInvalidation"],
                resources=[f"arn:aws:cloudfront::{self.account}:distribution/{web_cdn.distribution_id}"],
            )
        )

        instance_env = {
            "APP_ENV": cfg.name,
            "RELEASE_BRANCH": cfg.release_branch,
            "GIT_REPO": GIT_REPO,
            "AWS_REGION": self.region,
            "AWS_DEFAULT_REGION": self.region,
            "DB_SECRET_ARN": db.db_secret.secret_arn,
            "DB_SCHEMA": cfg.db_schema,
            "JWT_SECRET_ARN": jwt.secret_arn,
            "WARSAW_API_TOKEN_SECRET_ARN": db.warsaw_token.secret_arn,
            "DEPLOY_KEY_SECRET_ARN": db.deploy_key.secret_arn,
            "WEB_BUCKET": bucket.bucket_name,
            "WEB_DISTRIBUTION_ID": web_cdn.distribution_id,
            "API_URL": api_url,
            "INGEST_SCHEDULE": cfg.ingest_schedule,
            "INGEST_GEOCODE_LIMIT": str(cfg.geocode_limit),
            "DB_POOL_SIZE": "5",
        }
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "mkdir -p /etc/warszawa",
            "cat > /etc/warszawa/instance.env <<'ENV'",
            *[f'{k}="{v}"' for k, v in instance_env.items()],  # quoted: values contain spaces
            "ENV",
            (EC2_DIR / "bootstrap.sh").read_text().replace("__AGENT__", (EC2_DIR / "agent.sh").read_text().rstrip()),
        )

        box = ec2.Instance(
            self,
            "Box",
            instance_name=f"warszawa-{cfg.name}",
            vpc=db.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=db.app_sg,
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE4_GRAVITON, ec2.InstanceSize.MICRO),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64, cached_in_context=True
            ),
            role=role,
            user_data=user_data,
            user_data_causes_replacement=True,  # the box is stateless: new bootstrap = new box
            require_imdsv2=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(16, volume_type=ec2.EbsDeviceVolumeType.GP3, encrypted=True),
                )
            ],
        )
        ec2.CfnEIPAssociation(self, "IpAssoc", allocation_id=eip.attr_allocation_id, instance_id=box.instance_id)

        cdk.CfnOutput(self, "ApiUrl", value=api_url)
        cdk.CfnOutput(self, "WebUrl", value=web_url)
        cdk.CfnOutput(self, "InstanceId", value=box.instance_id)
        cdk.CfnOutput(self, "PublicIp", value=eip.attr_public_ip)

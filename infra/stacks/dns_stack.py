import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from constructs import Construct


class ZoneStack(cdk.Stack):
    """Route53 zone for the Namecheap domain. Deployed first, on its own, so its nameservers
    never change: set them at Namecheap (NameServers output), then deploy WarszawaLiveDns."""

    def __init__(self, scope: Construct, id: str, *, domain: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.domain = domain
        self.zone = route53.PublicHostedZone(self, "Zone", zone_name=domain)
        self.zone.apply_removal_policy(cdk.RemovalPolicy.RETAIN)
        cdk.CfnOutput(self, "NameServers", value=cdk.Fn.join(",", self.zone.hosted_zone_name_servers))


class DnsStack(cdk.Stack):
    """One CloudFront certificate for the apex and every subdomain (www, api, dev, api-dev)."""

    def __init__(self, scope: Construct, id: str, *, zone: ZoneStack, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.domain = zone.domain
        self.zone = zone.zone
        # CloudFront only accepts certificates from us-east-1. Our SCP blocks CloudFormation there,
        # so this construct creates the certificate through a Lambda making ACM API calls instead.
        self.certificate = acm.DnsValidatedCertificate(
            self,
            "CdnCertificate",
            domain_name=self.domain,
            subject_alternative_names=[f"*.{self.domain}"],
            hosted_zone=self.zone,
            region="us-east-1",
            cleanup_route53_records=True,
        )
        cdk.CfnOutput(self, "CertificateArn", value=self.certificate.certificate_arn)

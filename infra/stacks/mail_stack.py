import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_ses as ses
from constructs import Construct

from stacks.dns_stack import ZoneStack


class MailStack(cdk.Stack):
    """Amazon SES sending identity for the domain: account verification and password-reset mails
    (backend/app/mail.py). DKIM (Easy DKIM, 2048-bit) and a custom MAIL FROM subdomain (SPF) are
    published into the Route53 zone automatically; DMARC starts at p=none.

    SES starts in the sandbox (only verified recipients, 200 mails/day) until AWS grants production
    access for the account; that is an account setting, not part of this stack.
    """

    def __init__(self, scope: Construct, id: str, *, zone: ZoneStack, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        domain = zone.domain
        self.identity = ses.EmailIdentity(
            self,
            "Domain",
            identity=ses.Identity.public_hosted_zone(zone.zone),
            mail_from_domain=f"mail.{domain}",
            dkim_signing=True,
        )
        route53.TxtRecord(
            self,
            "Dmarc",
            zone=zone.zone,
            record_name="_dmarc",
            values=["v=DMARC1; p=none; adkim=s; aspf=r"],
        )
        self.identity_arn = f"arn:aws:ses:{self.region}:{self.account}:identity/{domain}"
        cdk.CfnOutput(self, "IdentityArn", value=self.identity_arn)

    def grant_send(self, role: iam.IRole, sender: str) -> None:
        role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail"],
                resources=[self.identity_arn],
                conditions={"StringEquals": {"ses:FromAddress": sender}},
            )
        )

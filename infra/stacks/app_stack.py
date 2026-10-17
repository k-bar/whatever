from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from stacks.db_stack import DbStack

BUNDLE = Path(__file__).resolve().parent.parent / "build" / "lambda"


class AppStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, db: DbStack, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        if not (BUNDLE / "app").exists():
            raise RuntimeError("Lambda bundle missing: run infra/build_lambda.sh first")
        code = lambda_.Code.from_asset(str(BUNDLE))

        env = {
            "DB_SECRET_ARN": db.db_secret.secret_arn,
            "JWT_SECRET_ARN": db.jwt_secret.secret_arn,
            "WARSAW_API_TOKEN_SECRET_ARN": db.warsaw_token.secret_arn,
            "DB_POOL_SIZE": "1",
        }
        common = dict(
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            code=code,
            environment=env,
        )

        self.api_fn = lambda_.Function(
            self,
            "Api",
            handler="app.lambda_handler.api",
            memory_size=1024,
            timeout=cdk.Duration.seconds(30),  # migrations run through this function too
            log_group=logs.LogGroup(
                self, "ApiLogs", retention=logs.RetentionDays.TWO_WEEKS, removal_policy=cdk.RemovalPolicy.DESTROY
            ),
            **common,
        )
        url = self.api_fn.add_function_url(auth_type=lambda_.FunctionUrlAuthType.NONE)  # CORS: FastAPI

        ingest_fn = lambda_.Function(
            self,
            "Ingest",
            handler="app.lambda_handler.ingest",
            memory_size=1024,
            timeout=cdk.Duration.minutes(15),
            log_group=logs.LogGroup(
                self, "IngestLogs", retention=logs.RetentionDays.TWO_WEEKS, removal_policy=cdk.RemovalPolicy.DESTROY
            ),
            **common,
        )

        for secret in (db.db_secret, db.jwt_secret, db.warsaw_token):
            secret.grant_read(self.api_fn)
            secret.grant_read(ingest_fn)

        # 3 sources x 150 lookups x 1.1 s (Nominatim limit) stays under the 15 min Lambda cap
        events.Rule(
            self,
            "HourlyIngest",
            schedule=events.Schedule.cron(minute="17"),
            targets=[
                targets.LambdaFunction(
                    ingest_fn, event=events.RuleTargetInput.from_object({"geocode_limit": 150}), retry_attempts=0
                )
            ],
        )

        cdk.CfnOutput(self, "ApiUrl", value=url.url)
        cdk.CfnOutput(self, "ApiFunctionName", value=self.api_fn.function_name)
        cdk.CfnOutput(self, "IngestFunctionName", value=ingest_fn.function_name)

#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# vim: tabstop=2 shiftwidth=2 softtabstop=2 expandtab

import os

from aws_cdk import (
    core,
    aws_ec2,
    aws_ecr,
    aws_ecs,
    aws_ecs_patterns,
    aws_iam,
    aws_s3 as s3,
    aws_applicationautoscaling
)

#TODO: divide stacks: vpc, redis, ecs cluster

class RssFeedTransBotEcsStack(core.Stack):

  def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
    super().__init__(scope, id, **kwargs)

    # The code that defines your stack goes here
    vpc_name = self.node.try_get_context("vpc_name")
    vpc = aws_ec2.Vpc.from_lookup(self, "VPC",
      is_default=False,
      vpc_name=vpc_name)

    s3_bucket_name = self.node.try_get_context('s3_bucket_name')
    s3_bucket = s3.Bucket.from_bucket_name(self, id, s3_bucket_name)

    cluster = aws_ecs.Cluster(self, "ECSCluster",
      cluster_name="rssfeed-trans-bot",
      vpc=vpc
    )

    task_role_policy_doc = aws_iam.PolicyDocument()
    task_role_policy_doc.add_statements(aws_iam.PolicyStatement(**{
      "effect": aws_iam.Effect.ALLOW,
      "resources": [s3_bucket.bucket_arn, "{}/*".format(s3_bucket.bucket_arn)],
      "actions": ["s3:AbortMultipartUpload",
        "s3:GetBucketLocation",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:ListBucketMultipartUploads",
        "s3:PutObject"]
    }))

    task_role_policy_doc.add_statements(aws_iam.PolicyStatement(**{
      "effect": aws_iam.Effect.ALLOW,
      "resources": ["*"],
      "actions": ["ses:SendEmail"]
    }))

    task_role_role = aws_iam.Role(self, 'ecsScheduledTaskRole',
      role_name='ecsRssFeedTransTaskRole',
      assumed_by=aws_iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      inline_policies={
        'ecsRssfeedTransBot': task_role_policy_doc
      }
    )

    # repository = aws_ecr.Repository(self, "Repository",
    #   repository_name="transbot/rssfeed")
    #
    # task_def = aws_ecs.FargateTaskDefinition(self, "SchFargateTaskDef", **{
    #   "cpu": 512,
    #   "memory_limit_mib": 1024,
    #   "task_role": task_role_role
    # })
    # t = aws_ecs_patterns.ScheduledFargateTaskDefinitionOptions(task_definition=task_def)

    #XXX: ECS Fargate Task Scheduling using existing Security Group #5213
    # https://github.com/aws/aws-cdk/issues/5213
    ecs_scheduled_task = aws_ecs_patterns.ScheduledFargateTask(self, "ScheduledTask",
      cluster=cluster,
      # scheduled_fargate_task_definition_options=t,
      scheduled_fargate_task_image_options={
        #https://github.com/aws/aws-cdk/issues/3646
        "image": aws_ecs.ContainerImage.from_ecr_repository(repository, tag="0.1"),
        "cpu": 512,
        "memory_limit_mib": 1024,
        "environment": {
          "ELASTICACHE_HOST": "localhost",
          "DRY_RUN": "false"
        }
      },
      schedule=aws_applicationautoscaling.Schedule.cron(minute="0/15"),
      subnet_selection=aws_ec2.SubnetSelection(subnet_type=aws_ec2.SubnetType.PRIVATE),
      vpc=vpc
  )

_env = core.Environment(
  account=os.environ["CDK_DEFAULT_ACCOUNT"],
  region=os.environ["CDK_DEFAULT_REGION"])

app = core.App()
RssFeedTransBotEcsStack(app, "rss-feed-trans-bot-on-ecs", env=_env)
app.synth()

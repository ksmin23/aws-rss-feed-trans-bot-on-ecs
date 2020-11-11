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
    aws_events,
    aws_events_targets,
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

    #XXX: ECS Fargate Task Scheduling using existing Security Group #5213
    # https://github.com/aws/aws-cdk/issues/5213
    # https://stackoverflow.com/questions/59067514/aws-cdk-ecs-task-scheduling-specify-existing-securitygroup
    task = aws_ecs.FargateTaskDefinition(self, 'TaskDef',
      cpu=512,
      memory_limit_mib=1024,
      task_role=task_role_role
    )
    #XXX: execution_role does not be created

    repository_arn = aws_ecr.Repository.arn_for_local_repository(
      "transbot/rssfeed",
      self,
      core.Aws.ACCOUNT_ID)

    # repository = aws_ecr.Repository.from_repository_arn(self, "Repository",
    #   repository_arn=repository_arn)
    #
    # jsii.errors.JSIIError: "repositoryArn" is a late-bound value,
    # and therefore "repositoryName" is required. Use `fromRepositoryAttributes` instead
    repository = aws_ecr.Repository.from_repository_attributes(self, "Repository",
      repository_arn=repository_arn,
      repository_name="transbot/rssfeed")

    task.add_container('ContainerImg',
      image=aws_ecs.ContainerImage.from_ecr_repository(repository, tag="0.1"),
      environment={
        "ELASTICACHE_HOST": "localhost",
        "DRY_RUN": "false"
      }
    )
    #TODO: how to create logging
    # https://stackoverflow.com/questions/59838175/how-to-create-logging-for-ecs-task-definition

    # See https://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html
    event_schedule = dict(zip(['minute', 'hour', 'month', 'week_day', 'year'],
      self.node.try_get_context('event_schedule').split(' ')))

    scheduled_event_rule = aws_events.Rule(self, 'RssFeedScheduledRule',
      enabled=False,
      schedule=aws_events.Schedule.cron(**event_schedule))

    sg_use_elasticache = aws_ec2.SecurityGroup.from_security_group_id(self, "RedisClientSG",
      security_group_id="sg-0e187e1b14b2a01d0", # use-default-redis, sg-01234
      mutable=False
    )

    sg_ecs_cron_task = aws_ec2.SecurityGroup.from_security_group_id(self, "EcsCronTaskSG",
      security_group_id="sg-0ba7c0fc2c05c55d1", # cron-r-8382, sg-01234
      mutable=False
    )

    scheduled_event_rule.add_target(aws_events_targets.EcsTask(cluster=cluster,
      task_definition=task,
      security_groups=[sg_ecs_cron_task, sg_use_elasticache],
      subnet_selection=aws_ec2.SubnetSelection(subnet_type=aws_ec2.SubnetType.PRIVATE)))

    # task_def = aws_ecs.FargateTaskDefinition(self, "SchFargateTaskDef", **{
    #   "cpu": 512,
    #   "memory_limit_mib": 1024,
    #   "task_role": task_role_role
    # })
    # t = aws_ecs_patterns.ScheduledFargateTaskDefinitionOptions(task_definition=task_def)

    #XXX: ECS Fargate Task Scheduling using existing Security Group #5213
    # https://github.com/aws/aws-cdk/issues/5213
    # https://stackoverflow.com/questions/59067514/aws-cdk-ecs-task-scheduling-specify-existing-securitygroup
    # ecs_scheduled_task = aws_ecs_patterns.ScheduledFargateTask(self, "ScheduledTask",
    #   cluster=cluster,
    #   # scheduled_fargate_task_definition_options=t,
    #   scheduled_fargate_task_image_options={
    #     #https://github.com/aws/aws-cdk/issues/3646
    #     "image": aws_ecs.ContainerImage.from_ecr_repository(repository, tag="0.1"),
    #     "cpu": 512,
    #     "memory_limit_mib": 1024,
    #     "environment": {
    #       "ELASTICACHE_HOST": "localhost",
    #       "DRY_RUN": "false"
    #     }
    #   },
    #   schedule=aws_applicationautoscaling.Schedule.cron(minute="0/15"),
    #   subnet_selection=aws_ec2.SubnetSelection(subnet_type=aws_ec2.SubnetType.PRIVATE),
    #   vpc=vpc)

_env = core.Environment(
  account=os.environ["CDK_DEFAULT_ACCOUNT"],
  region=os.environ["CDK_DEFAULT_REGION"])

app = core.App()
RssFeedTransBotEcsStack(app, "rss-feed-trans-bot-on-ecs", env=_env)
app.synth()

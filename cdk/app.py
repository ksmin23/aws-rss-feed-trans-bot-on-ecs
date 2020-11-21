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
    aws_elasticache,
    aws_events,
    aws_events_targets,
    aws_iam,
    aws_logs,
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
      is_default=True,
      vpc_name=vpc_name)

    s3_bucket_name = self.node.try_get_context('s3_bucket_name')
    s3_bucket = s3.Bucket.from_bucket_name(self, id, s3_bucket_name)

    sg_use_elasticache = aws_ec2.SecurityGroup(self, 'RssFeedTransBotCacheClientSG',
      vpc=vpc,
      allow_all_outbound=True,
      description='security group for redis client used rss feed trans bot',
      security_group_name='use-rss-feed-trans-bot-redis'
    )
    core.Tags.of(sg_use_elasticache).add('Name', 'use-rss-feed-trans-bot-redis')

    sg_elasticache = aws_ec2.SecurityGroup(self, 'RssFeedTransBotCacheSG',
      vpc=vpc,
      allow_all_outbound=True,
      description='security group for redis used rss feed trans bot',
      security_group_name='rss-feed-trans-bot-redis'
    )
    core.Tags.of(sg_elasticache).add('Name', 'rss-feed-trans-bot-redis')

    sg_elasticache.add_ingress_rule(peer=sg_use_elasticache, connection=aws_ec2.Port.tcp(6379), description='use-rss-feed-trans-bot-redis')

    elasticache_subnet_group = aws_elasticache.CfnSubnetGroup(self, 'RssFeedTransBotCacheSubnetGroup',
      description='subnet group for rss-feed-trans-bot-redis',
      subnet_ids=vpc.select_subnets(subnet_type=aws_ec2.SubnetType.PRIVATE).subnet_ids,
      cache_subnet_group_name='rss-feed-trans-bot-redis'
    )

    translated_feed_cache = aws_elasticache.CfnCacheCluster(self, 'RssFeedTransBotCache',
      cache_node_type='cache.t3.small',
      num_cache_nodes=1,
      engine='redis',
      engine_version='5.0.5',
      auto_minor_version_upgrade=False,
      cluster_name='rss-feed-trans-bot-redis',
      snapshot_retention_limit=3,
      snapshot_window='17:00-19:00',
      preferred_maintenance_window='mon:19:00-mon:20:30',
      #XXX: Do not use referece for 'cache_subnet_group_name' - https://github.com/aws/aws-cdk/issues/3098
      cache_subnet_group_name=elasticache_subnet_group.cache_subnet_group_name, # Redis cluster goes to wrong VPC
      vpc_security_group_ids=[sg_elasticache.security_group_id]
    )

    #XXX: If you're going to launch your cluster in an Amazon VPC, you need to create a subnet group before you start creating a cluster.
    # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-elasticache-cache-cluster.html#cfn-elasticache-cachecluster-cachesubnetgroupname
    translated_feed_cache.add_depends_on(elasticache_subnet_group)

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

    task_execution_role = aws_iam.Role(self, 'ecsScheduledTaskRole',
      role_name='ecsRssFeedTransTaskExecutionRole',
      assumed_by=aws_iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      inline_policies = {
        "s3access": task_role_policy_doc
      },
      managed_policies=[
        aws_iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy"),
        aws_iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSESFullAccess")
      ]
    )

    #XXX: ECS Fargate Task Scheduling using existing Security Group #5213
    # https://github.com/aws/aws-cdk/issues/5213
    # https://stackoverflow.com/questions/59067514/aws-cdk-ecs-task-scheduling-specify-existing-securitygroup
    task = aws_ecs.FargateTaskDefinition(self, 'TaskDef',
      cpu=512,
      memory_limit_mib=1024,
      # execution_role=task_execution_role #TODO: can not attach Execution Role
      task_role=task_execution_role
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
      image=aws_ecs.ContainerImage.from_ecr_repository(repository, tag="0.3"),
      environment={
        "ELASTICACHE_HOST": translated_feed_cache.attr_redis_endpoint_address,
        "DRY_RUN": "false",
        "TRANSLATE_ALL_FEEDS": "false"
      },
      logging=aws_ecs.LogDriver.aws_logs(stream_prefix="ecs",
        log_group=aws_logs.LogGroup(self, 
          "ECSContainerLogGroup",
          log_group_name="/ecs/rss-feed-trans-bot",
          retention=aws_logs.RetentionDays.ONE_DAY)
      )
    )

    # See https://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html
    event_schedule = dict(zip(['minute', 'hour', 'month', 'week_day', 'year'],
      self.node.try_get_context('event_schedule').split(' ')))

    scheduled_event_rule = aws_events.Rule(self, 'RssFeedScheduledRule',
      enabled=False,
      schedule=aws_events.Schedule.cron(**event_schedule))

    ecs_events_role = aws_iam.Role(self, 'ecsEventsRole',
      role_name='ecsRssFeedTransEventsRole',
      assumed_by=aws_iam.ServicePrincipal('events.amazonaws.com'),
      managed_policies=[
        aws_iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceEventsRole")
      ]
    )

    scheduled_event_rule.add_target(aws_events_targets.EcsTask(cluster=cluster,
      task_definition=task,
      role=ecs_events_role,
      security_groups=[sg_use_elasticache],
      subnet_selection=aws_ec2.SubnetSelection(subnet_type=aws_ec2.SubnetType.PRIVATE)))

_env = core.Environment(
  account=os.environ["CDK_DEFAULT_ACCOUNT"],
  region=os.environ["CDK_DEFAULT_REGION"])

app = core.App()
RssFeedTransBotEcsStack(app, "rss-feed-trans-bot-on-ecs", env=_env)
app.synth()

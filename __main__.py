"""An AWS Python Pulumi program"""
import pulumi
import pulumi_aws as aws
import ipaddress, math
import base64
from pulumi_gcp import serviceaccount, iam, storage


config = pulumi.Config()

#Creating VPC
base_vpc_cidr = config.require('vpc_cidr_block')
myvpc = aws.ec2.Vpc(config.require('vpc_name'),
    cidr_block=base_vpc_cidr,
    instance_tenancy="default",
    tags={
        "Name": config.require('vpc_name'),
    })

#getting list of available zones in the region
available = aws.get_availability_zones(state="available")
print(available.names)

public_subnets =[]
private_subnets = []
subet_cidr = []

ipi = ipaddress.ip_interface(base_vpc_cidr)
base_cidr = int(str(ipi.network).split('/')[1])
cidr_add = math.ceil(math.sqrt(len(available.names) * 2))

# creates an IPv4Network
base_ip = ipaddress.IPv4Network(base_vpc_cidr)
#generates a list of subnets from the base_ip network and divides the base IP address range into subnets
subnets = list(base_ip.subnets(new_prefix=base_cidr + cidr_add))
#providing both the index and the subnet in each iteration
for index, subnet in enumerate(subnets):
    subet_cidr.append(str(subnet))

print("All subnet cidr blocks : ", subet_cidr)

#Creating 3 private subnets & 3 public subnets in loop on different aws regions
subet_cidr_count = 0
for i in range(3):
    #if available zones in region is less than 3 then breaking the loop
    if i > len(available.names) - 1:
        break

    public_subnets.append(aws.ec2.Subnet("public_subnet_" + str(i+1),
                                      vpc_id=myvpc.id,
                                      cidr_block=subet_cidr[subet_cidr_count],
                                      availability_zone= available.names[i],
                                      map_public_ip_on_launch = True,
                                      tags={
                                          "Name": "public_subnet_" + str(i+1),
                                      }))

    private_subnets.append(aws.ec2.Subnet("private_subnet_" + str(i+1),
                                       vpc_id=myvpc.id,
                                       cidr_block=subet_cidr[subet_cidr_count + 1],
                                       availability_zone= available.names[i],
                                       tags={
                                           "Name": "private_subnet_" + str(i+1),
                                       }))
    subet_cidr_count += 2

#creating internet gateway
igw = aws.ec2.InternetGateway(config.require('igw_name'),
    tags={
        "Name": config.require('igw_name'),
    })
#attaching internet gateway
myvpc_igw_attachment = aws.ec2.InternetGatewayAttachment(config.require('vpc_igw_attachment'),
    internet_gateway_id= igw.id,
    vpc_id=myvpc.id)

#Creating public route table
public_RT = aws.ec2.RouteTable(config.require('public_route_table'),
    vpc_id=myvpc.id,
    routes=[
        aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            gateway_id=igw.id,
        )
    ],
    tags={
        "Name": config.require('public_route_table'),
    })

#Creating private route table
private_RT = aws.ec2.RouteTable(config.require('priavte_route_table'),
    vpc_id=myvpc.id,
    tags={
        "Name": config.require('priavte_route_table'),
    })

#Creating load balancer Security group
load_balancer_security_grp = aws.ec2.SecurityGroup("load_balancer_sg",
    description="load_balancer_sg",
    vpc_id=myvpc.id, # TODO fix this
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            description="LB security group port 80",
            from_port=80,
            to_port=80,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
        aws.ec2.SecurityGroupIngressArgs(
            description="LB security group port 443",
            from_port=443,
            to_port=443,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
        from_port=0,
        to_port=0,
        protocol="-1",
        cidr_blocks=["0.0.0.0/0"],
    )],
    tags={
        "Name": "lb_security_group_name",
    })

#Creating application Security group
app_security_grp = aws.ec2.SecurityGroup("application security group",
    description="application security group",
    vpc_id=myvpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            description="application security group port 22",
            from_port=22,
            to_port=22,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
        aws.ec2.SecurityGroupIngressArgs(
            description="application security group port 8080",
            from_port=8080,
            to_port=8080,
            protocol="tcp",
            security_groups=[load_balancer_security_grp.id],
        ),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        from_port=0,
        to_port=0,
        protocol="-1",
        cidr_blocks=["0.0.0.0/0"],
    )],
    tags={
        "Name": config.require('security_group_name'),
    })

#Creating database Security group
database_security_grp = aws.ec2.SecurityGroup("database_security_grp",
    description="database_security_grp",
    vpc_id=myvpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        description="database security group port 3306",
        from_port=3306,
        to_port=3306,
        protocol="tcp",
        security_groups=[app_security_grp.id],
    ),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        from_port=0,
        to_port=0,
        protocol="-1",
        cidr_blocks=["0.0.0.0/0"],
    )],
    tags={
        "Name": config.require('db_security_group_name'),
    })


# Creating RDS Parameter group
mariadbgrp = aws.rds.ParameterGroup("mariadbgrp",
    family="mariadb10.6",
    tags={
        "Name": "mariadb-grp",
    })


private_subnet_group = aws.rds.SubnetGroup(
    'mydb_subnetgroup',
    subnet_ids=[subnet.id for subnet in private_subnets])


#Creating RDS

mariadb_rds = aws.rds.Instance("mariadb_rds",
    allocated_storage=config.require('db_allocated_storage'),
    engine=config.require('database'),
    engine_version=config.require('engine_version'),
    instance_class=config.require('db_instance_class'),
    parameter_group_name=mariadbgrp.name,
    skip_final_snapshot=True,
    db_subnet_group_name=private_subnet_group.name,
    vpc_security_group_ids=[database_security_grp],
    publicly_accessible=False,
    username=config.require('username'),
    password=config.require('password'),
    db_name=config.require('db_name'),
    multi_az=False,
    identifier=config.require('db_identifier'),
    )

print("MariaDb: ", mariadb_rds)
#getting key-pair
key_pair = aws.ec2.get_key_pair(key_name=config.require('key_name'),
    include_public_key=True,)

# Create an IAM role
ec2_role = aws.iam.Role("ec2Role",
    assume_role_policy=pulumi.Output.from_input("""{
        "Version":"2012-10-17",
        "Statement":[{
            "Action":"sts:AssumeRole",
            "Principal":{
                "Service":"ec2.amazonaws.com"
            },
            "Effect":"Allow",
            "Sid":""
        }]
    }""")
)

# Attach the CloudWatchAgentServerPolicy policy to the IAM role
cloudwatch_agent_server_policy_attachment = aws.iam.RolePolicyAttachment("cloudwatchPolicyAttachment",
    role=ec2_role.id,
    policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
)

# Create an IAM policy for `PutItem` DynamoDB action
custom_policy_ec2 = aws.iam.Policy('customPolicyForEc2Sns',
    description='EC2 to publish on sns',
    policy='''{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["sns:Publish"],
            "Resource": "*"
         }]
    }'''
)

aws.iam.RolePolicyAttachment('lambdaRoleCustomPolicy',
    role=ec2_role.name,
    policy_arn=custom_policy_ec2.arn)

# Define an Instance Profile that incorporates the defined role
instance_profile = aws.iam.InstanceProfile(
    "myInstanceProfile",
    role=ec2_role.name
)

username = mariadb_rds.username
password = mariadb_rds.password
db_instance_endpoint = mariadb_rds.endpoint
region_name = aws.get_region().name
# Create an SNS Topic
sns_topic = aws.sns.Topic(config.require('sns_topic_name'))

user_data_script = pulumi.Output.all(username, password,db_instance_endpoint,sns_topic.arn,region_name).apply(lambda args: f"""#!/bin/bash
ENV_FILE="/opt/application.properties"
echo "username={args[0]}" >> $ENV_FILE
echo "password={args[1]}" >> $ENV_FILE
echo "endpoint={args[2]}" >> $ENV_FILE
echo "sns_topic_arn={args[3]}" >> $ENV_FILE
echo "region_name={args[4]}" >> $ENV_FILE
chown csye6225:csye6225 $ENV_FILE
chmod 755 $ENV_FILE
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/cloudwatch-config.json -s
""")


#EC2 Launch template
ec2_launch_template = aws.ec2.LaunchTemplate("ec2_launch_template",
    block_device_mappings=[aws.ec2.LaunchTemplateBlockDeviceMappingArgs(
        device_name=config.require('device_name'),
        ebs=aws.ec2.LaunchTemplateBlockDeviceMappingEbsArgs(
            volume_size=config.require('volume_size'),
            volume_type=config.require('volume_type'),
            delete_on_termination="true",
        ),
    )],

    iam_instance_profile=aws.ec2.LaunchTemplateIamInstanceProfileArgs(
        name=instance_profile.name,
    ),
    image_id=config.require('myami'),
    instance_type=config.require('instance_type'),
    key_name=key_pair.key_name,

    network_interfaces=[aws.ec2.LaunchTemplateNetworkInterfaceArgs(
        associate_public_ip_address='true',
        # subnet_id=public_subnets[0].id,
        security_groups=[app_security_grp.id],

    )],
    disable_api_termination=False,
    tag_specifications=[aws.ec2.LaunchTemplateTagSpecificationArgs(
        resource_type="instance",
        tags={
            "Name": config.require('ec2_template'),
        },
    )],
    user_data=pulumi.Output.all(user_data_script).apply(lambda args: base64.b64encode(args[0].encode("utf-8")).decode("utf-8")))

#Creating Target Group
target_group = aws.lb.TargetGroup("csye6225-target-group",
    port=config.require('target_grp_port'),
    protocol="HTTP",
    vpc_id=myvpc.id,
    target_type='instance',
    ip_address_type='ipv4',
    health_check=aws.lb.TargetGroupHealthCheckArgs(
        protocol=config.require('health_chk_portol'),
        port=config.require('health_chk_port'),
        path=config.require('health_chk_path'),
    ))

#Auto Scaling Group
auto_scaling_group = aws.autoscaling.Group("auto_scaling_group",
    # availability_zones=available.names,
    vpc_zone_identifiers=public_subnets,
    desired_capacity=config.require('desired_capacity'),
    max_size=config.require('max_size'),
    min_size=config.require('min_size'),
    default_cooldown=config.require('default_cooldown'),
    launch_template=aws.autoscaling.GroupLaunchTemplateArgs(
        id=ec2_launch_template.id,
        version="$Latest",
    ),
    target_group_arns=[target_group.arn])# target group arn to relate instances)

# Scale up policy: increments by 1 when average CPU usage is above 5%
scale_up_policy = aws.autoscaling.Policy("scaleUpPolicy",
    adjustment_type="ChangeInCapacity",
    policy_type=config.require('policy_type'),
    scaling_adjustment=config.require('scaling_up_cnt'),  # increment by 1
    autoscaling_group_name=auto_scaling_group.name,
)

# Scale down policy: decrements by 1 when average CPU usage is above 3%
scale_down_policy = aws.autoscaling.Policy("scaleDownPolicy",
    adjustment_type="ChangeInCapacity",
    policy_type=config.require('policy_type'),
    scaling_adjustment=config.require('scaling_down_cnt'),  # decrement by 1
    autoscaling_group_name=auto_scaling_group.name,
)

scale_up_alarm = aws.cloudwatch.MetricAlarm("scale_up_alarm",
    alarm_description="This metric monitors ec2 average cpu utilization",
    comparison_operator="GreaterThanThreshold",
    evaluation_periods=config.require('evaluation_periods'),
    insufficient_data_actions=[],
    metric_name=config.require('metric_name'),
    namespace=config.require('namespace'),
    period=config.require('alarm_period'),
    statistic="Average",
    threshold=config.require('scale_up_threshold'),
    dimensions={
        "AutoScalingGroupName": auto_scaling_group.name,
    },
    alarm_actions=[scale_up_policy.arn])

scale_down_alarm = aws.cloudwatch.MetricAlarm("scale_down_alarm",
    alarm_description="This metric monitors ec2 average cpu utilization",
    comparison_operator="LessThanThreshold",
    evaluation_periods=config.require('evaluation_periods'),
    insufficient_data_actions=[],
    metric_name=config.require('metric_name'),
    namespace=config.require('namespace'),
    period=config.require('alarm_period'),
    statistic="Average",
    threshold=config.require('scale_down_threshold'),
    dimensions={
        "AutoScalingGroupName": auto_scaling_group.name,
    },
    alarm_actions=[scale_down_policy.arn])


# Create load balancer
load_balancer = aws.lb.LoadBalancer('csye6225-load-balancer',
  internal=False,
  load_balancer_type='application',
  subnets=public_subnets,
  security_groups=[load_balancer_security_grp.id],
)

lb_listener = aws.lb.Listener("lb_listener",
    load_balancer_arn=load_balancer.arn,
    port=80,
    protocol="HTTP",
    default_actions=[aws.lb.ListenerDefaultActionArgs(
        type="forward",
        target_group_arn=target_group.arn,
    )])


selected = aws.route53.get_zone(name=config.require('domain_name'))
http = aws.route53.Record("http",
    zone_id=selected.zone_id,
    name=config.require('domain_name'),
    allow_overwrite= True,
    type="A",
    aliases=[aws.route53.RecordAliasArgs(
            name=load_balancer.dns_name,
            zone_id=load_balancer.zone_id,
            evaluate_target_health=False,
    )])


#associating public subnets to public RT and private subnets to private RT
for i in range(len(public_subnets)):
    aws.ec2.RouteTableAssociation("public_table_subnet_association_" + str(i+1),
                                  subnet_id=public_subnets[i].id,
                                  route_table_id=public_RT.id)

    aws.ec2.RouteTableAssociation("private_table_subnet_association_" + str(i+1),
                                  subnet_id=private_subnets[i].id,
                                  route_table_id=private_RT.id)

# Create a DynamoDB table
dynamodb_table = aws.dynamodb.Table(config.require('ddb_table_name'),
    attributes=[
        aws.dynamodb.TableAttributeArgs(
            name="unique_id",
            type="S",
        ),
    ],
    hash_key="unique_id",
    read_capacity=5,
    write_capacity=5,
)
#creating service account
service_account = serviceaccount.Account("csye6225-serviceAccount",
    account_id="csye6225-serviceaccount",
    display_name="csye6225_serviceAccount")

# Add 'Storage Object Admin' iam policy binding to the service account
binding = storage.BucketIAMMember('submission-bucket',
    bucket=config.require('bucket_name'),
    role='roles/storage.legacyBucketOwner',
    member=pulumi.Output.concat('serviceAccount:', service_account.email))

gcp_key = serviceaccount.Key("csye6225-gcp-key",
    service_account_id=service_account.account_id)

# IAM role for lambda execution
lambda_role = aws.iam.Role('lambdaRole',
    assume_role_policy=pulumi.Output.from_input({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Principal": {
                "Service": "lambda.amazonaws.com",
            },
            "Effect": "Allow",
            "Sid": "",
        }],
    }))


# Create an IAM policy for `PutItem` DynamoDB action
custom_policy = aws.iam.Policy('customPolicyForLambda',
    description='Put Item and SES policy',
    policy='''{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["dynamodb:PutItem","ses:SendEmail"],
            "Resource": "*"
         }]
    }'''
)

aws.iam.RolePolicyAttachment('lambdaRolePolicy',
    role=lambda_role.name,
    policy_arn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole')

aws.iam.RolePolicyAttachment('lambdaRoleCustomPolicy',
    role=lambda_role.name,
    policy_arn=custom_policy.arn)

# Creating a Lambda Layer
layer = aws.lambda_.LayerVersion("lambda_layer",
    code=pulumi.FileArchive("../lambda-layer-requests-python3.9-x86_64.zip"),
    layer_name="supporting_packages_layer",
    compatible_runtimes=["python3.10"],
)

# Create a lambda function
lambda_func = aws.lambda_.Function('myLambdaFunction',
    code=pulumi.AssetArchive({
        '.': pulumi.FileArchive('../serverless/lambda_handler_folder'),
    }),
    role=lambda_role.arn,
    handler='lambda_function.lambda_handler',
    runtime='python3.10',
    publish=True,
    timeout=120,
    layers=[layer.arn], # assigning the layer
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "ddb_table_name": dynamodb_table.name,
            "region": aws.get_region().name,
            "gcp_key": gcp_key.private_key,
            "bucket_name": config.require('bucket_name'),
            "source_email": config.require('source_email')

        },
    )
)

# Give permission from SNS to Lambda
aws.lambda_.Permission('lambdaPermission',
    action="lambda:InvokeFunction",
    function=lambda_func.name,
    principal="sns.amazonaws.com",
    source_arn=sns_topic.arn
)

# Create an SNS Topic Subscription to Lambda
subscription = aws.sns.TopicSubscription('myTopicSubscription',
    protocol="lambda",
    endpoint=lambda_func.arn,
    topic=sns_topic.arn
)

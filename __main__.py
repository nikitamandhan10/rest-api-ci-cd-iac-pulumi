"""An AWS Python Pulumi program"""
import pulumi
import pulumi_aws as aws
import ipaddress, math

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

#Creating application Security group
app_security_grp = aws.ec2.SecurityGroup("application security group",
    description="application security group",
    vpc_id=myvpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        description="application security group port 22",
        from_port=22,
        to_port=22,
        protocol="tcp",
        cidr_blocks=["0.0.0.0/0"],
    ),
        aws.ec2.SecurityGroupIngressArgs(
            description="application security group port 80",
            from_port=80,
            to_port=80,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
aws.ec2.SecurityGroupIngressArgs(
            description="application security group port 443",
            from_port=443,
            to_port=443,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
aws.ec2.SecurityGroupIngressArgs(
            description="application security group port 8080",
            from_port=8080,
            to_port=8080,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
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

# Define an Instance Profile that incorporates the defined role
instance_profile = aws.iam.InstanceProfile(
    "myInstanceProfile",
    role=ec2_role.name
)


username = mariadb_rds.username
password = mariadb_rds.password
db_instance_endpoint = mariadb_rds.endpoint


user_data_script = pulumi.Output.all(username, password,db_instance_endpoint).apply(lambda args: f"""#!/bin/bash
ENV_FILE="/opt/application.properties"
echo "username={args[0]}" >> $ENV_FILE
echo "password={args[1]}" >> $ENV_FILE
echo "endpoint={args[2]}" >> $ENV_FILE
chown csye6225:csye6225 $ENV_FILE
chmod 755 $ENV_FILE
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/cloudwatch-config.json -s
""")

#creating ec2 instance
web = aws.ec2.Instance("web",
    ami=config.require('myami'),
    key_name=key_pair.key_name,
    user_data=user_data_script,
    instance_type=config.require('instance_type'),
    subnet_id=public_subnets[0].id,
    vpc_security_group_ids=[app_security_grp.id],
    iam_instance_profile=instance_profile.name,
    ebs_block_devices=[
        aws.ec2.InstanceEbsBlockDeviceArgs(
            volume_size=config.require('volume_size'),
            device_name=config.require('device_name'),
            volume_type= config.require('volume_type'),
            delete_on_termination=True,
        )
    ],
    disable_api_termination=False,
    tags={
        "Name": config.require('ec2_instance_name'),
    })

# Get the public IP address of the EC2 instance
instance_public_ip = web.public_ip

selected = aws.route53.get_zone(name=config.require('domain_name'))
http = aws.route53.Record("http",
    zone_id=selected.zone_id,
    name=config.require('domain_name'),
    allow_overwrite= True,
    type="A",
    ttl=60,
    records=[instance_public_ip])


#associating public subnets to public RT and private subnets to private RT
for i in range(len(public_subnets)):
    aws.ec2.RouteTableAssociation("public_table_subnet_association_" + str(i+1),
                                  subnet_id=public_subnets[i].id,
                                  route_table_id=public_RT.id)

    aws.ec2.RouteTableAssociation("private_table_subnet_association_" + str(i+1),
                                  subnet_id=private_subnets[i].id,
                                  route_table_id=private_RT.id)

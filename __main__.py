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

#Creating Security group
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

#getting my recently created AMI ID
myami = aws.ec2.get_ami(executable_users=["self"],
                        most_recent=True)

print(myami.id)

#getting key-pair
key_pair = aws.ec2.get_key_pair(key_name=config.require('key_name'),
    include_public_key=True,)

print("fingerprint", key_pair.fingerprint)
print("name", key_pair.key_name)
print("id", key_pair.id)


#creating ec2 instance
web = aws.ec2.Instance("web",
    ami=myami.id,
    key_name=key_pair.key_name,
    instance_type=config.require('instance_type'),
    subnet_id=public_subnets[0].id,
    vpc_security_group_ids=[app_security_grp.id],
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


#associating public subnets to public RT and private subnets to private RT
for i in range(len(public_subnets)):
    aws.ec2.RouteTableAssociation("public_table_subnet_association_" + str(i+1),
                                  subnet_id=public_subnets[i].id,
                                  route_table_id=public_RT.id)

    aws.ec2.RouteTableAssociation("private_table_subnet_association_" + str(i+1),
                                  subnet_id=private_subnets[i].id,
                                  route_table_id=private_RT.id)

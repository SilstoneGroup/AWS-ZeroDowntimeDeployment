import argparse
import boto3
import logging
from botocore.exceptions import ClientError

credentials_path = "~/.aws/credentials"
region_path = "~/.aws/config"

# for simplicity we are including access id and key in the code here!
# for security this is a BIG BIG NO!!!! please create config on the
# above paths for region and credentials or use environment variables

region = "sample-region"                                       # for now assuming a region e.g us-west-1
access_id = "sample-access-id"
access_key = "sample-access-key"

# key_name = "aws_keypair"                                # for now single keypair name, function for general keypair creation
# sample_load_balancer_name = "sampleLoadBalancer"     #provide load balancer name if there are multiple. Assuming the name here

class zeroDowntimeDeploy(object):
    def __init__(self):
        self.client = boto3.client('ec2', region_name=region, aws_access_key_id=access_id, aws_secret_access_key=access_key)
        self.elb = boto3.client('elbv2', region_name=region, aws_access_key_id=access_id, aws_secret_access_key=access_key)
        self.vpc = ""
        self.credentials_path = credentials_path
        # self.avaibility_zones = []

    def image_exists(self, ami_id=None):
        # checks if given ami id image exists
        try:
            self.client.describe_images(ExecutableUsers=['self',], ImageIds=[ami_id,])
        except ClientError as e:
            if e.response['Error']['Code'] == "InvalidAMIID.Malformed":
                log.error("Invalid ami id! : " + str(ami_id))
            elif e.response['Error']['Code'] == "InvalidAMIID.NotFound":
                log.error("AMI Id doesn't exist!")
            else:
                log.error("Exception found : "+ str(e))
            return False
        return True

    def create_instances_with_ami(self, ami_id=None, instance_type="t2.micro", min_instance=1, max_instance=1, avaibility_zone=None, subnet_id=None):
        try:
            # create a new EC2 instance
            instances = self.client.run_instances(ImageId=ami_id, MinCount=min_instance, MaxCount=max_instance,\
             InstanceType=instance_type, KeyName=self.get_keypair_name(), SubnetId=subnet_id, Placement={"AvailabilityZone": avaibility_zone})
            # waiting for the instance to be running otherwise issue arises while adding it to elb
            waiter = self.client.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instances["Instances"][0]["InstanceId"]])
            return instances["Instances"][0]["InstanceId"]
        except ClientError as e:
            raise Exception("Exception in creating new instance of type : {} and AMI Id: {}".format(instance_type, new_ami))
            return None

    def get_all_instances(self, ami_id=None):
        return self.client.describe_instances(Filters=[{"Name" : "image-id", "Values" :[ami_id,]},])
        # return self.client.describe_instances(ImageIds=[ami_id])

    def get_availibility_zones_with_subnet(self, ami_id=None):
        # return self.client.describe_images(ImageIds=[ami_id])
        avaibility_zones = []
        for reservation in self.get_all_instances(ami_id)["Reservations"]:
            for instance in reservation["Instances"]:
                self.vpc = instance["VpcId"]
                avaibility_zones.append((instance["Placement"]["AvailabilityZone"], instance["SubnetId"]))
        return avaibility_zones

    def get_all_instance_ids(self, ami_id=None):
        instance_ids = []
        for reservation in self.get_all_instances(ami_id)["Reservations"]:
            for instance in reservation["Instances"]:
                if instance["State"]["Name"] == "running":
                    instance_ids.append(instance["InstanceId"])
        return instance_ids

    def get_load_balancer_name(self, instances=None):
        # TODO: revisit this logic
        try:
            arns = self.get_target_group_with_instances(instances=instances)
            log.info("Target arn : {0} and lb-arn : {1}".format(arns[0], arns[1]))
        except Exception as e:
            raise(e)

        try:
            all_load_balancers = self.elb.describe_load_balancers()
            # log.info("All load balancers : " + str(all_load_balancers))
        except Exception as e:
            raise Exception("Exception in fetching all load balancers : "+ str(e))

        for load_balancer in all_load_balancers["LoadBalancers"]:
            if load_balancer["LoadBalancerArn"] == arns[1]:
                return [load_balancer["LoadBalancerName"], arns[0]]
        raise Exception("There are 0 load balancers configured for this account!")

    def describe_all_target_groups(self):
        target_groups = self.elb.describe_target_groups()["TargetGroups"]
        # log.info("All target groups : " + str(target_groups))
        return target_groups

    def get_target_group_with_instances(self, instances=None):
        # TODO: check when there are multiple arns in the LoadBalancerArn list --? when can this happen?
        try:
            target_groups = self.describe_all_target_groups()
            for group in target_groups:
                # hit target health API to know which targets are associated with the group
                targets = self.elb.describe_target_health(TargetGroupArn=group["TargetGroupArn"])["TargetHealthDescriptions"]
                for target in targets:
                    if target["Target"]["Id"] in instances:
                        return [group["TargetGroupArn"], group["LoadBalancerArns"][0]]
        except Exception as e:
            raise Exception("Exception in target group find! : " + str(e))
            return [False, False]

    def register_targets_to_elb(self, target_group_arn=None, instance_ids=None):
        instance_dict = dict({})
        final_instance_list = []
        log.debug("Instance id to register : " + str(instance_ids))
        try:
            for id in instance_ids:
                instance_dict["Id"] = id
                final_instance_list.append(instance_dict)
                instance_dict={}

            log.info("***** Final instance list to register: " + str(final_instance_list) + " *****")
            return self.elb.register_targets(TargetGroupArn=target_group_arn, Targets=final_instance_list)
        except Exception as e:
            print("Exception in register : "+ str(e))
            raise Exception("Exception encountered in register instances to elb : " + str(e.response["Error"]["Message"]))

    def deregister_targets_to_elb(self, target_group_arn=None, instance_ids=None):
        instance_dict = dict({})
        final_instance_list = []
        log.debug("Instance id to deregister : " + str(instance_ids))
        try:
            for id in instance_ids:
                instance_dict["Id"] = id
                final_instance_list.append(instance_dict)
                instance_dict={}

            log.info("Final instance list to deregister: " + str(final_instance_list))
            self.elb.deregister_targets(TargetGroupArn=target_group_arn, Targets=final_instance_list)
        except Exception as e:
            print("Exception in deregister : "+ str(e))
            raise Exception("Exception encountered in register instances to elb : " + str(e.response["Error"]["Message"]))

    def create_new_load_balancer(self, load_balancer_name=None):
        pass

    def get_keypair_name(self):
        # TODO: check if multiple keypairs are there
        try:
            return self.client.describe_key_pairs()["KeyPairs"][0]["KeyName"]
        except Exception as e:
            raise Exception("Error in getting all keypairs : " + str(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("old_ami", type=str, help="Old AMI Id to copy from!")
    parser.add_argument("new_ami", type=str, help="New AMI Id to copy to!")
    parser.add_argument("-v", "--verbosity", action="store_true", help="Increase verbosity of the output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO) if args.verbosity else logging.basicConfig(level=logging.ERROR)
    log = logging.getLogger("ZDP")

    if(args.old_ami == args.new_ami):
        log.error("Please provide different OLD AMI Id and NEW AMI Id!")
        exit()

    old_instances = []
    new_instances = []
    try:
        # do_op(old_ami=args.old_ami, new_ami=args.new_ami, loglevel=loglevel)
        zdp = zeroDowntimeDeploy()
        log.info("***** Check if given old and new ami ids are valid! *****")
        # if not zdp.image_exists(args.new_ami) and not zdp.image_exists(args.old_ami):
        if not zdp.image_exists(args.old_ami) or not zdp.image_exists(args.new_ami):
            exit()

        log.info("***** Get all instances of old ami! *****")
        old_instances = zdp.get_all_instance_ids(args.old_ami)
        log.debug("Count : " + str(len(old_instances)))
        log.error("Old instance ids : " + str(old_instances))

        log.info("***** Get avaibility zones and Subnet ids of old ami instances! *****")
        avaibility_zones = zdp.get_availibility_zones_with_subnet(args.old_ami)
        log.error("All avaibility zones : " + str(avaibility_zones))

        log.info("***** Get vpc of old ami instances! *****")
        log.error("Vpc Id : " + str(zdp.vpc))

        log.info("***** Get load balancer attached to the instances of old ami! *****")
        load_balancer_name = zdp.get_load_balancer_name(old_instances)
        log.error("Load balancer name : " + str(load_balancer_name[0]))

        log.info("***** Get all instances of new ami! *****")
        new_instances = zdp.get_all_instance_ids(args.new_ami)
        log.error("New instance ids : " + str(new_instances))

        if (len(new_instances) == 0):            # new instances not created from ami id
            #spawn new instances with given avaibility_zone and subnet id
            log.info("***** Creating instances with new ami with required avaibility_zones and subnets *****")
            for instance in avaibility_zones:
                new_instances.append(zdp.create_instances_with_ami(ami_id=args.new_ami, avaibility_zone=instance[0], subnet_id=instance[1]))

        log.info("***** Get all instances of new ami! *****")
        new_instances = zdp.get_all_instance_ids(args.new_ami)
        log.error("New instance ids : " + str(new_instances))

        log.info("***** Register new instances to the elb! *****")
        zdp.register_targets_to_elb(instance_ids=new_instances, target_group_arn=load_balancer_name[1])

        log.info("***** Deregister old instances from the elb! *****")
        zdp.deregister_targets_to_elb(instance_ids=old_instances, target_group_arn=load_balancer_name[1])

        log.info("***** Verify that new setup works! *****")
        # some verification script or request to be called through public
        # internet and response should be checked!
    except Exception as e:
        log.error("***** ERROR *****\nFailed to execute the script successfully : " + str(e))
        exit()

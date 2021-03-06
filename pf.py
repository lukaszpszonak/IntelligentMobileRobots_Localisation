from geometry_msgs.msg import Pose, PoseArray, Quaternion
from pf_base import PFLocaliserBase
import math
import rospy
import numpy as np
import scipy as sp
from util import rotateQuaternion, getHeading
import random
import copy
from time import time

TAU = math.pi * 2


class PFLocaliser(PFLocaliserBase):
    # Initializing Parameters   
    def __init__(self):
        # Call the Superclass Constructor
        super(PFLocaliser, self).__init__()
        
        # Set motion model parameters
        self.ODOM_ROTATION_NOISE = 0.05 #0.5 #5          # Odometry model rotation noise
        self.ODOM_TRANSLATION_NOISE = 0.05 #0.5 #5      # Odometry model x-axis noise (forward)
        self.ODOM_DRIFT_NOISE = 0.05  #0.5 #5           # Odometry model y-axis noise (side-to-side) 

        # Sensor Model Parameters
        self.NUMBER_PREDICTED_READINGS = 30      # Number of readings from the laser scan.  
                                                 # Based on the readings, the weights are predicted.
        self.NUM_PARTICLES = 500                 # Number of particles

        #Define the noise parameters for the initial particle cloud 
        self.INITIAL_GAUSS_SD = 1 #10 #50        # Gaussian Standard Deviation 
        self.INITIAL_VONMISES_SD = 5 #50 #100    # VonMises Standard Deviation 

        #Define the noise Parameters used to update the particle cloud later
        self.GAUSS_SD = 1 #5 #10
        self.VONMISES_SD = 50 #25 #75

      
    #The Roulette Wheel Index Selection - used for resampling in Monte Carlo Localisation
    #Returns the index of the heavy weights more often than low weights
    def roulette_wheel_index_selection(self, weightArray, weight_sum):
        value = random.random() * weight_sum  
        for j in range(len(weightArray)):
            value -= weightArray[j]
            index = j
            if value <= 0: #break the loop under this condition
                    break 
        return index #return the index of the heavy weights


   #Defining a function that adds noise in Monte Carlo Localisation
    def add_noise(self, pose):

        pose.position.x += random.gauss(0, self.GAUSS_SD) * self.ODOM_TRANSLATION_NOISE   # Adding noise to x coordinate 
        pose.position.y += random.gauss(0, self.GAUSS_SD) * self.ODOM_DRIFT_NOISE   #Add noise to y coordinate
        rotationAngle = ((random.vonmisesvariate(0, self.VONMISES_SD) - math.pi) * self.ODOM_ROTATION_NOISE) #compute the noise
        pose.orientation = rotateQuaternion(pose.orientation, rotationAngle) # Add the noise to rotation angles
        return pose


    # Set Particle Cloud to Initial Pose Plus Noise   
    def initialise_particle_cloud(self, initialpose):
   
        array = PoseArray()                                             
        for i in range(self.NUM_PARTICLES):                                  
            CurrentPose = Pose()                                                                    
            xnoise = random.gauss(0, self.INITIAL_GAUSS_SD) * self.ODOM_TRANSLATION_NOISE  #add Gaussian Standard Deviation and store it as x noise
            ynoise = random.gauss(0, self.INITIAL_GAUSS_SD) * self.ODOM_DRIFT_NOISE  #add Gaussian Standard Deviation and store it as y noise
            
            CurrentPose.position.x = initialpose.pose.pose.position.x + xnoise #add the noise to the current x coordinate
            CurrentPose.position.y = initialpose.pose.pose.position.y + ynoise #add the noise to the current y coordinate

            rotationAngle = ((random.vonmisesvariate(0, self.INITIAL_VONMISES_SD) - math.pi) * self.ODOM_ROTATION_NOISE) #add VonMises SD and 
            #store it as the rotation angle
            CurrentPose.orientation = rotateQuaternion(initialpose.pose.pose.orientation, rotationAngle) #rotate of a value of the rotation angle

            array.poses.append(CurrentPose) #update the array
        return array
	

    #Update Particlecloud based on the map and scan
    def update_particle_cloud(self, scan):  #The following resamples the particle cloud based on the particle weights,
    #they are obtained from the sensor model   
        array = PoseArray()
        
        particle_weights = []
        weight_sum = 0   #zeroing the sum of weights                                               
        for pose in self.particlecloud.poses:  #this for loop summs up the weights of the particles and updates the sum of weights                         
            currentWeight = self.sensor_model.get_weight(scan, pose)
            particle_weights.append(currentWeight)
            weight_sum += currentWeight
       
       #This is the actual Monte Carlo Localisation 
       #Here the Roulette Wheel Algorithm selects, with high probability, the higher-weight particles and adds noise to them in order to
       #generate resampled particles - more converged towards optima.   
        for i in range(len(self.particlecloud.poses)): 
            index = self.roulette_wheel_index_selection(particle_weights, weight_sum)       
            array.poses.append(copy.deepcopy(self.particlecloud.poses[index])) 
        for i, CurrentPose in enumerate(array.poses):
		    CurrentPose = self.add_noise(CurrentPose)
        print "Number of particles: " + str(len(array.poses))
        self.particlecloud = array 
       
    #Below function estimates the pose, given the particle cloud
    def estimate_pose(self):
        
        est_pose = Pose()
        x_total = 0
        y_total = 0  
        qx_total = 0 #quaternion x sum
        qy_total = 0 #quaternion y sum
        qz_total = 0 #quaternion z sum
        qw_total = 0 #quaternion omega sum

        for num, i in enumerate(self.particlecloud.poses):
            x_total += i.position.x
            y_total += i.position.y
            qz_total += i.orientation.z
            qw_total += i.orientation.w

        est_pose.position.x = x_total / self.NUM_PARTICLES
        est_pose.position.y = y_total / self.NUM_PARTICLES
        est_pose.orientation.z = qz_total / self.NUM_PARTICLES
        est_pose.orientation.w = qw_total / self.NUM_PARTICLES

        print('X position: ', est_pose.position.x)
        print('Y position: ', est_pose.position.y)
        
        return est_pose


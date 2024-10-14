from functions_for_data_processing import get_data, plot_raw_data, process_raw_vicon_data,plot_vicon_data\
,dyn_model_culomb_tires,\
    process_vicon_data_kinematics,throttle_dynamics_data_processing,steering_dynamics_data_processing
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import os



# chose what stated to forward propagate (the others will be taken from the data, this can highlight individual parts of the model)


# select data folder NOTE: this assumes that the current directory is DART
#folder_path = 'System_identification_data_processing/Data/90_model_validation_long_term_predictions'  # the battery was very low for this one
#folder_path = 'System_identification_data_processing/Data/91_model_validation_long_term_predictions_fast'
#folder_path = 'System_identification_data_processing/Data/91_free_driving_16_sept_2024'
#folder_path = 'System_identification_data_processing/Data/91_free_driving_16_sept_2024_slow'
#folder_path = 'System_identification_data_processing/Data/free_driving_steer_rate_testing_16_sept_2024'

#folder_path = 'System_identification_data_processing/Data/81_throttle_ramps_only_steer03'
folder_path = 'System_identification_data_processing/Data/circles_27_sept_2024'



steering_friction_flag = True
pitch_dynamics_flag = False

# the model gives you the derivatives of it's own states, so you can integrate them to get the states in the new time instant
dynamic_model = dyn_model_culomb_tires(steering_friction_flag,pitch_dynamics_flag)



# process data

# process data

steps_shift = 5 # decide to filter more or less the vicon data


# check if there is a processed vicon data file already
file_name = 'processed_vicon_data_throttle_steering_dynamics.csv'
# Check if the CSV file exists in the folder
file_path = os.path.join(folder_path, file_name)

if not os.path.isfile(file_path):
    df_raw_data = get_data(folder_path)

    
    # add throttle with time integrated throttle
    filtered_throttle = throttle_dynamics_data_processing(df_raw_data)
    df_raw_data['throttle filtered'] = filtered_throttle

    # add steering angle with time integated version
    st_angle_vec_FEuler, st_vec_FEuler = steering_dynamics_data_processing(df_raw_data)
    # over-write the actual data with the forward integrated data
    df_raw_data['steering angle filtered'] = st_angle_vec_FEuler
    df_raw_data['steering filtered'] = st_vec_FEuler

    # process kinematics and dynamics
    df_kinematics = process_vicon_data_kinematics(df_raw_data,steps_shift)
    df = process_raw_vicon_data(df_kinematics,steps_shift)

    #save the processed data file
    df.to_csv(file_path, index=False)
    print(f"File '{file_path}' saved.")
else:
    print(f"File '{file_path}' already exists, loading data.")
    df = pd.read_csv(file_path)




if folder_path == 'System_identification_data_processing/Data/circles_27_sept_2024':

    df1 = df[df['vicon time']>1]
    df1 = df1[df1['vicon time']<375]

    df2 = df[df['vicon time']>377]
    df2 = df2[df2['vicon time']<830]

    df3 = df[df['vicon time']>860]
    df3 = df3[df3['vicon time']<1000]

    df = pd.concat([df1,df2,df3])
    df = df[df['vx body']>0.5]
    #df = df[df['vx body']<2.5]
    df = df[df['ax body']<2]
    df = df[df['ax body']>-1]








# plot raw data
ax0,ax1,ax2 = plot_raw_data(df)

# plot vicon related data (longitudinal and lateral velocities, yaw rate related)
ax_wheel_f_alpha,ax_wheel_r_alpha,ax_total_force_front,\
ax_total_force_rear,ax_lat_force,ax_long_force,\
ax_acc_x_body,ax_acc_y_body,ax_acc_w = plot_vicon_data(df) 




# producing long term predictions
columns_to_extract = ['vx body', 'vy body', 'w', 'throttle filtered' ,'steering filtered','throttle','steering']
input_data = df[columns_to_extract].to_numpy()



# plot long term predictions
acc_x_model = np.zeros(df.shape[0])
acc_y_model = np.zeros(df.shape[0])
acc_w_model = np.zeros(df.shape[0])

for i in range(0,df.shape[0]):
    acc = dynamic_model.forward(input_data[i,:])
    acc_x_model[i] = acc[0]
    acc_y_model[i] = acc[1]
    acc_w_model[i] = acc[2]


# plot model putputs
fig1, ((ax_acc_x,ax_acc_y,ax_acc_w)) = plt.subplots(3, 1, figsize=(10, 6), constrained_layout=True)

# plot longitudinal accleeartion
ax_acc_x.plot(df['vicon time'].to_numpy(),df['ax body'].to_numpy(),label='ax body',color='dodgerblue')
ax_acc_x.plot(df['vicon time'].to_numpy(),acc_x_model,color='k',label='model output')

ax_acc_x.legend()

# plot lateral accleeartion
ax_acc_y.plot(df['vicon time'].to_numpy(),df['ay body'].to_numpy(),label='ay body',color='orangered')
ax_acc_y.plot(df['vicon time'].to_numpy(),acc_y_model,color='k',label='model output')
ax_acc_y.legend()

# plot yaw rate
ax_acc_w.plot(df['vicon time'].to_numpy(),df['acc_w'].to_numpy(),label='acc_w',color='purple')
ax_acc_w.plot(df['vicon time'].to_numpy(),acc_w_model,color='k',label='model output')
ax_acc_w.legend()






plt.show()



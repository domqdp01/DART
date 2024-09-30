import os
import glob
import pandas as pd
import numpy as np
from scipy.interpolate import UnivariateSpline, CubicSpline
from matplotlib import pyplot as plt
import torch
from scipy.signal import savgol_filter

def directly_measured_model_parameters():
    # from vicon system measurements
    theta_correction = 0.00768628716468811 # error between vehicle axis and vicon system reference axis
    lr_reference = 0.115  #0.11650    # (measureing it wit a tape measure it's 0.1150) reference point location taken by the vicon system measured from the rear wheel
    l_lateral_shift_reference = -0.01 # the reference point is shifted laterally by this amount 
    #COM_positon = 0.084 #0.09375 #centre of mass position measured from the rear wheel

    # car parameters
    l = 0.1735 # [m]length of the car (from wheel to wheel)
    m = 1.580 # mass [kg]
    m_front_wheel = 0.847 #[kg] mass pushing down on the front wheel
    m_rear_wheel = 0.733 #[kg] mass pushing down on the rear wheel

    #COM_positon = m_front_wheel / m # measured from the back
    # lr * mr = lf * mf
    # lf = lr * mr/mf
    # l = lr + lr * mr/mf
    # l = lr (1+mr/mf)
    COM_positon = l / (1+m_rear_wheel/m_front_wheel)
    lr = COM_positon
    lf = l-lr
    # Automatically adjust following parameters according to tweaked values
    l_COM = lr_reference - COM_positon

    #lateral measurements
    l_width = 0.08 # width of the car is 8 cm
    m_left_wheels = 0.794 # mass pushing down on the left wheels
    m_right_wheels = 0.805 # mass pushing down on the right wheels
    # so ok the centre of mass is pretty much in the middle of the car so won't add this to the derivations


    Jz = 1/12 * m *(l**2+l_width**2) #0.006513 # Moment of inertia of uniform rectangle of shape 0.1735 x 0.8 NOTE this is an approximation cause the mass is not uniformly distributed


    return [theta_correction, l_COM, l_lateral_shift_reference ,lr, lf, Jz, m,m_front_wheel,m_rear_wheel]


def model_parameters():
    # collect fitted model parameters here so that they can be easily accessed

    # motor model  (from fitting both friction and motor model at the same time) 
    a_m =  25.82439422607422
    b_m =  5.084076881408691
    c_m =  -0.15623189508914948
    d_m =  0.6883225440979004

    # rolling friction model
    a_f =  1.4945894479751587
    b_f =  3.9869790077209473
    c_f =  0.7107542157173157
    d_f =  -0.11705359816551208

    # steering angle curve --from fitting on vicon data
    a_s =  1.4141819477081299
    b_s =  0.36395299434661865
    c_s =  -0.0004661157727241516 - 0.03 # littel adjustment to allign the tire curves
    d_s =  0.517351508140564
    e_s =  1.0095096826553345


    # a_s =  1.2842596769332886
    # b_s =  0.3637458086013794
    # c_s =  -0.05655587837100029
    # d_s =  0.3872089385986328
    # e_s =  1.2888582944869995


    # Front wheel parameters:
    d_t_f =  -0.8545126914978027
    c_t_f =  0.8446515202522278
    b_t_f =  8.199576377868652
    # Rear wheel parameters:
    d_t_r =  -0.8819053173065186
    c_t_r =  0.9599690437316895
    b_t_r =  10.797096252441406


    #additional friction due to steering angle
    a_stfr =  2.3015944957733154
    b_stfr =  1.2494314908981323
    d_stfr =  1.5295004844665527
    e_stfr =  -1.6932182312011719
    f_stfr =  7.634786605834961
    g_stfr =  12.37331485748291

    # steering dynamics

    max_st_dot = 9.395668777594302
    fixed_delay_stdn = 5.904623074022001
    k_stdn = 0.24112116182648466


    # pitch dynamics parameters:
    w_natural_Hz_pitch = 2.0380144119262695
    k_f_pitch = -0.11680269241333008
    k_r_pitch = -0.5
    # roll dynamics parameters:
    w_natural_Hz_roll = 5.10979700088501
    k_f_roll = -0.04334288835525513
    k_r_roll = -0.5


    return [a_m, b_m, c_m, d_m,
            a_f, b_f, c_f, d_f,
            a_s, b_s, c_s, d_s, e_s,
            d_t_f, c_t_f, b_t_f,d_t_r, c_t_r, b_t_r,
            a_stfr, b_stfr,d_stfr,e_stfr,f_stfr,g_stfr,
            max_st_dot,fixed_delay_stdn,k_stdn,
            w_natural_Hz_pitch,k_f_pitch,k_r_pitch,
            w_natural_Hz_roll,k_f_roll,k_r_roll]



def get_data(folder_path):
    import csv
    import os

    # This function gets (or produces) the merged data files from the specified folder
    print('Getting data')
    print('Looking for file " merged_files.csv "  in folder "', folder_path,'"')

    file_name = 'merged_files.csv'
    # Check if the CSV file exists in the folder
    file_path = os.path.join(folder_path, file_name)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        print('The CSV file exists in the specified folder.')

    else:
        print('The CSV file does not already exist in the specified folder. Proceding with file generation.')
        merge_data_files_from_a_folder(folder_path)

    #recording_name_train = file_name
    df = pd.read_csv(file_path)
    print('Data succesfully loaded.')
    return df



def merge_data_files_from_a_folder(folder_path):
    #this method creates a single file from all .csv files in the specified folder

    # Output file name and path
    file_name = 'merged_files.csv'
    output_file_path = folder_path + '/' + file_name

    # Get all CSV file paths in the folder
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    csv_files.sort(key=lambda x: os.path.basename(x))

    dataframes = []
    timing_offset = 0

    # Read each CSV file and store it in the dataframes list
    for csv_file in csv_files:
        df = pd.read_csv(csv_file)

        #sometimes the files have some initial lines where all values are zero, so just remove them
        df = df[df['elapsed time sensors'] != 0.0]

        # set throttle to 0 when safety is off
        df['throttle'][df['safety_value'] == 0.0] = 0.0

        # reset time in each file to start from zero
        df['elapsed time sensors'] -= df['elapsed time sensors'].iloc[0]
        df['elapsed time sensors'] += timing_offset

        

        if 'vicon time' in df.keys():
            df['vicon time'] -= df['vicon time'].iloc[0]
            df['vicon time'] += timing_offset
            dt = np.average(df['vicon time'].diff().to_numpy()[1:]) # evaluate dt
            timing_offset = df['vicon time'].iloc[-1] + dt 
            # stitch position together so to avoid instantaneous change of position
            if dataframes:
                df['vicon x'] = df['vicon x'] - df['vicon x'].iloc[0]
                df['vicon y'] = df['vicon y'] - df['vicon y'].iloc[0]

                # now x and y must be rotated to allign with the previous file's last orientation
                theta = dataframes[-1]['vicon yaw'].iloc[-1] - df['vicon yaw'].iloc[0]
                # Compute the new x and y coordinates after rotation
                rotated_x = df['vicon x'].to_numpy() * np.cos(theta) - df['vicon y'].to_numpy() * np.sin(theta)
                rotated_y = df['vicon x'].to_numpy() * np.sin(theta) + df['vicon y'].to_numpy() * np.cos(theta)

                # this matches up the translation
                df['vicon x'] = rotated_x + dataframes[-1]['vicon x'].iloc[-1]
                df['vicon y'] = rotated_y + dataframes[-1]['vicon y'].iloc[-1]

                #not stich together the rotation angle
                df['vicon yaw'] = df['vicon yaw'] + theta #- df['vicon yaw'].iloc[0] + dataframes[-1]['vicon yaw'].iloc[-1]
                # correct yaw that may now be less than pi
                #df['vicon yaw'] = (df['vicon yaw'] + np.pi) % (2 * np.pi) - np.pi
        else:
            #update timing offset
            #extract safety off data and fix issues with timing
            dt = np.average(df['elapsed time sensors'].diff().to_numpy()[1:]) # evaluate dt
            timing_offset = df['elapsed time sensors'].iloc[-1] + dt # each file will have a dt timegap between it and the next file
        


        
        dataframes.append(df)

    # Concatenate all DataFrames into a single DataFrame vertically
    merged_df = pd.concat(dataframes, axis=0, ignore_index=True)

    #write merged csv file
    merged_df.to_csv(output_file_path, index=False)

    print('Merging complete. Merged file saved as:', output_file_path)
    return output_file_path #, num_lines



def evaluate_delay(signal1,signal2):
    # outputs delay expressed in vector index jumps
    # we assume that the signals are arrays of the same length
    if len(signal1) == len(signal2):
    
        # Use numpy's correlate function to find cross-correlation
        cross_corr = np.correlate(signal1, signal2, mode='full')
        #the length of the cross_corr vector will be N + N - 1
        # in position N you find the cross correlation for 0 delay
        # signal 1 is kept still and signal 2 is moved across. 
        # So if signal 2 is a delayed version of signal 1, the maximum
        # value of the cross correlation will accur before position N. (N means no delay)

        # Find the index of the maximum correlation
        delay_indexes = (len(signal1)) - (np.argmax(cross_corr)+1)  # plus one is needed cause np.argmax gives you the index of where that is

        return delay_indexes
    else:
        print('signals not of the same length! Stopping delay evaluation')


def process_raw_data_steering(df):
    
    # evaluate measured steering angle by doing inverse of kinematic bicycle model (only when velocity is higher than 0.8 m/s)
    # Note that dataset should not contain high velocities since the kinematic bicycle model will fail, and measured steering angle would be wrong
    L = 0.175 # distance between front and rear axels
    elapsed_time_vec = df['elapsed time sensors'][df['vel encoder'] > 0.8].to_numpy()
    #steering_delayed = df['steering delayed'][df['vel encoder'] > 0.8].to_numpy()
    steering = df['steering'][df['vel encoder'] > 0.8].to_numpy()

    vel_encoder = df['vel encoder'][df['vel encoder'] > 0.8].to_numpy()
    w_vec = df['W (IMU)'][df['vel encoder'] > 0.8].to_numpy()
    steering_angle= np.arctan2(w_vec * L ,  vel_encoder) 

    d = {'elapsed time sensors': elapsed_time_vec,
        #'W (IMU)': w_vec,
        'steering angle': steering_angle,
        #'steering delayed' : steering_delayed,
        'steering' : steering}

    df_steering_angle = pd.DataFrame(data=d)

    return df_steering_angle




def throttle_dynamics(df_raw_data,d_m):
    # add filtered throttle
    T = df_raw_data['vicon time'].diff().mean()  # Calculate the average time step
    # Filter coefficient in the new sampling frequency
    d_m_100Hz = 0.01/(0.01+(0.1/d_m-0.1)) #convert to new sampling frequency

    # Initialize the filtered steering angle list
    #filtered_throttle = [df_raw_data['throttle'].iloc[0]]
    filtered_throttle = np.zeros(df_raw_data.shape[0])
    # Apply the first-order filter
    for i in range(1, len(df_raw_data)):
        filtered_value = d_m_100Hz * df_raw_data['throttle'].iloc[i-1] + (1 - d_m_100Hz) * filtered_throttle[i-1]
        filtered_throttle[i] = filtered_value


    return filtered_throttle


def steering_dynamics(df_raw_data,a_s,b_s,c_s,d_s,e_s,max_st_dot,fixed_delay_stdn,k_stdn):

    # -------------------  forard integrate the steering signal  -------------------
    # NOTE this is a bit of a hack
    T = df_raw_data['vicon time'].diff().mean()  # Calculate the average time step
    
    # re-run the model to get the plot of the best prediction

    # Convert the best fixed_delay to an integer
    best_delay_int = int(np.round(fixed_delay_stdn))

    # Evaluate the shifted steering signal using the best fixed delay
    steering_time_shifted = df_raw_data['steering'].shift(best_delay_int, fill_value=0).to_numpy()

    # Initialize variables for the steering prediction
    st = 0
    st_vec_optuna = np.zeros(df_raw_data.shape[0])
    st_vec_angle_optuna = np.zeros(df_raw_data.shape[0])

    # Loop through the data to compute the predicted steering angles
    for k in range(1, df_raw_data.shape[0]):
        # Calculate the rate of change of steering (steering dot)
        st_dot = (steering_time_shifted[k-1] - st) / T * k_stdn
        # Apply max_st_dot limits
        st_dot = np.min([st_dot, max_st_dot])
        st_dot = np.max([st_dot, -max_st_dot])
        
        # Update the steering value with the time step
        st += st_dot * T
        
        # Compute the steering angle using the two models with weights
        w_s = 0.5 * (np.tanh(30 * (st + c_s)) + 1)
        steering_angle1 = b_s * np.tanh(a_s * (st + c_s))
        steering_angle2 = d_s * np.tanh(e_s * (st + c_s))
        
        # Combine the two steering angles using the weight
        steering_angle = (w_s) * steering_angle1 + (1 - w_s) * steering_angle2
        
        # Store the predicted steering angle
        st_vec_angle_optuna[k] = steering_angle
        st_vec_optuna[k] = st

    return st_vec_angle_optuna, st_vec_optuna



def plot_raw_data(df):
    plotting_time_vec = df['elapsed time sensors'].to_numpy()

    fig1, ((ax0, ax1, ax2)) = plt.subplots(3, 1, figsize=(10, 6), constrained_layout=True)
    ax0.set_title('dt check')
    ax0.plot(np.diff(df['elapsed time sensors']), label="dt", color='gray')
    ax0.set_ylabel('dt [s]')
    ax0.set_xlabel('data point')
    ax0.legend()

    # plot raw data velocity vs throttle
    ax1.set_title('Raw Velocity vs throttle')
    ax1.plot(plotting_time_vec, df['vel encoder'].to_numpy(), label="V encoder [m/s]", color='dodgerblue')
    ax1.plot(plotting_time_vec, df['throttle'].to_numpy(), label="throttle raw []", color='gray')
    # Create a background where the safety is disingaged
    mask = np.array(df['safety_value']) == 1
    ax1.fill_between(plotting_time_vec, ax1.get_ylim()[0], ax1.get_ylim()[1], where=mask, color='gray', alpha=0.1, label='safety value disingaged')
    ax1.set_xlabel('time [s]')
    ax1.legend()

    # plot raw data w vs steering
    ax2.set_title('Raw Omega')
    ax2.plot(plotting_time_vec, df['W (IMU)'].to_numpy(),label="omega IMU raw data [rad/s]", color='orchid')
    ax2.plot(plotting_time_vec, df['steering'].to_numpy(),label="steering raw []", color='pink') 
    ax2.fill_between(plotting_time_vec, ax2.get_ylim()[0], ax2.get_ylim()[1], where=mask, color='gray', alpha=0.1, label='safety value disingaged')
    ax2.set_xlabel('time [s]')
    ax2.legend()
    return ax0,ax1,ax2






def process_vicon_data_kinematics(df,steps_shift,theta_correction, l_COM, l_lateral_shift_reference):

    # resampling the robot data to have the same time as the vicon data
    from scipy.interpolate import interp1d

    # Step 1: Identify sensor time differences and extract sensor checkpoints
    sensor_time_diff = df['elapsed time sensors'].diff()

    # Times where sensor values change more than 0.01s (100Hz -> 10Hz)
    sensor_time = df['elapsed time sensors'][sensor_time_diff > 0.01].to_numpy()
    steering_at_checkpoints = df['steering'][sensor_time_diff > 0.01].to_numpy()

    # Step 2: Interpolate using Zero-Order Hold
    zoh_interp = interp1d(sensor_time, steering_at_checkpoints, kind='previous', bounds_error=False, fill_value="extrapolate")

    # Step 3: Apply interpolation to 'vicon time'
    df['steering'] = zoh_interp(df['vicon time'].to_numpy())

    
    robot2vicon_delay = 5 # samples delay between the robot and the vicon data # very important to get it right (you can see the robot reacting to throttle and steering inputs before they have happened otherwise)
    # this is beacause the lag between vicon-->laptop, and robot-->laptop is different. (The vicon data arrives sooner)

    # there is a timedelay between robot and vicon system. Ideally the right way to do this would be to shift BACKWARDS in time the robot data.
    # but equivalently we can shift FORWARDS in time the vicon data. This is done by shifting the vicon time backwards by the delay time.
    # This is ok since we just need the data to be consistent. but be aware of this
    df['vicon x'] = df['vicon x'].shift(+robot2vicon_delay)
    df['vicon y'] = df['vicon y'].shift(+robot2vicon_delay)
    df['vicon yaw'] = df['vicon yaw'].shift(+robot2vicon_delay)
    # account for fisrt values that will be NaN
    df['vicon x'].iloc[:robot2vicon_delay] = df['vicon x'].iloc[robot2vicon_delay]
    df['vicon y'].iloc[:robot2vicon_delay] = df['vicon y'].iloc[robot2vicon_delay]
    df['vicon yaw'].iloc[:robot2vicon_delay] = df['vicon yaw'].iloc[robot2vicon_delay]


    #  ---  relocating reference point to the centre of mass  ---
    df['vicon x'] = df['vicon x'] - l_COM*np.cos(df['vicon yaw']) - l_lateral_shift_reference*np.cos(df['vicon yaw']+np.pi/2)
    df['vicon y'] = df['vicon y'] - l_COM*np.sin(df['vicon yaw']) - l_lateral_shift_reference*np.sin(df['vicon yaw']+np.pi/2)
    # -----------------------------------------------------------


    # -----     KINEMATICS      ------
    df['unwrapped yaw'] = unwrap_hm(df['vicon yaw'].to_numpy()) + theta_correction

    time_vec_vicon = df['vicon time'].to_numpy() 

    # --- evaluate first time derivative ---

    shifted_time0 = df['vicon time'].shift(+steps_shift)
    shifted_x0 = df['vicon x'].shift(+steps_shift)
    shifted_y0 = df['vicon y'].shift(+steps_shift)
    shifted_yaw0 = df['unwrapped yaw'].shift(+steps_shift)

    shifted_time2 = df['vicon time'].shift(-steps_shift)
    shifted_x2 = df['vicon x'].shift(-steps_shift)
    shifted_y2 = df['vicon y'].shift(-steps_shift)
    shifted_yaw2 = df['unwrapped yaw'].shift(-steps_shift)


    # Finite differences
    df['vx_abs_filtered'] = (shifted_x2 - shifted_x0) / (shifted_time2 - shifted_time0)
    df['vy_abs_filtered'] = (shifted_y2 - shifted_y0) / (shifted_time2 - shifted_time0)
    df['w']  = (shifted_yaw2 - shifted_yaw0) / (shifted_time2 - shifted_time0)

    # Handle the last 5 elements (they will be NaN due to the shift)
    df['vx_abs_filtered'].iloc[-steps_shift:] = 0
    df['vy_abs_filtered'].iloc[-steps_shift:] = 0
    df['w'].iloc[-steps_shift:] = 0

    df['vx_abs_filtered'].iloc[:steps_shift] = 0
    df['vy_abs_filtered'].iloc[:steps_shift] = 0
    df['w'].iloc[:steps_shift] = 0



    # window_size = 10
    # poly_order = 1


    # --- evalaute second time derivative ---
    # Shifted values for steps_shift indices ahead
    shifted_vx0 = df['vx_abs_filtered'].shift(+steps_shift)
    shifted_vy0 = df['vy_abs_filtered'].shift(+steps_shift)
    shifted_w0 = df['w'].shift(+steps_shift)

    shifted_vx2 = df['vx_abs_filtered'].shift(-steps_shift)
    shifted_vy2 = df['vy_abs_filtered'].shift(-steps_shift)
    shifted_w2 = df['w'].shift(-steps_shift)

    # Calculate the finite differences for acceleration
    df['ax_abs_filtered_more'] = (shifted_vx2 - shifted_vx0) / (shifted_time2 - shifted_time0)
    df['ay_abs_filtered_more'] = (shifted_vy2 - shifted_vy0) / (shifted_time2 - shifted_time0)
    df['acc_w'] = (shifted_w2 - shifted_w0) / (shifted_time2 - shifted_time0)

    # Handle the last 5 elements (they will be NaN due to the shift)
    df['ax_abs_filtered_more'].iloc[-steps_shift:] = 0
    df['ay_abs_filtered_more'].iloc[-steps_shift:] = 0
    df['acc_w'].iloc[-steps_shift:] = 0

    df['ax_abs_filtered_more'].iloc[:steps_shift] = 0
    df['ay_abs_filtered_more'].iloc[:steps_shift] = 0
    df['acc_w'].iloc[:steps_shift] = 0


    # --- convert velocity and acceleration into body frame ---
    vx_body_vec = np.zeros(df.shape[0])
    vy_body_vec = np.zeros(df.shape[0])
    ax_body_vec_nocent = np.zeros(df.shape[0])
    ay_body_vec_nocent = np.zeros(df.shape[0])

    for i in range(df.shape[0]):
        rot_angle =  - df['unwrapped yaw'].iloc[i] # from global to body you need to rotate by -theta!

        R     = np.array([[ np.cos(rot_angle), -np.sin(rot_angle)],
                          [ np.sin(rot_angle),  np.cos(rot_angle)]])
        

        vxvy = np.expand_dims(np.array(df[['vx_abs_filtered','vy_abs_filtered']].iloc[i]),1)
        axay = np.expand_dims(np.array(df[['ax_abs_filtered_more','ay_abs_filtered_more']].iloc[i]),1)

        vxvy_body = R @ vxvy
        axay_nocent = R @ axay

        vx_body_vec[i],vy_body_vec[i] = vxvy_body[0], vxvy_body[1]
        ax_body_vec_nocent[i],ay_body_vec_nocent[i] = axay_nocent[0], axay_nocent[1]

    df['vx body'] = vx_body_vec
    df['vy body'] = vy_body_vec

    df['ax body no centrifugal'] = ax_body_vec_nocent
    df['ay body no centrifugal'] = ay_body_vec_nocent

    # add acceleration in own body frame
    accx_cent = + df['vy body'].to_numpy() * df['w'].to_numpy() 
    accy_cent = - df['vx body'].to_numpy() * df['w'].to_numpy()

    # add centrifugal forces to df
    df['ax body'] = accx_cent + df['ax body no centrifugal'].to_numpy()
    df['ay body'] = accy_cent + df['ay body no centrifugal'].to_numpy()
    return df



def process_raw_vicon_data(df,steps_shift):

    model_functions_obj = model_functions() # instantiate the model functions object

    [theta_correction, l_COM, l_lateral_shift_reference ,lr, lf, Jz, m,m_front_wheel,m_rear_wheel] = directly_measured_model_parameters()

    [a_m, b_m, c_m, d_m,
    a_f, b_f, c_f, d_f,
    a_s, b_s, c_s, d_s, e_s,
    d_t_f, c_t_f, b_t_f,d_t_r, c_t_r, b_t_r,
    a_stfr, b_stfr,d_stfr,e_stfr,f_stfr,g_stfr,
    max_st_dot,fixed_delay_stdn,k_stdn,
    w_natural_Hz_pitch,k_f_pitch,k_r_pitch,
    w_natural_Hz_roll,k_f_roll,k_r_roll]= model_parameters()


    # process kinematics from vicon data
    #df = process_vicon_data_kinematics(df,steps_shift,theta_correction, l_COM, l_lateral_shift_reference)


    # Evaluate steering angle and slip angles as they can be useful to tweak the parameters relative to the measuring system
    
    # evaluate steering angle if it is not provided
    if 'steering angle' in df.columns:
        steering_angle = df['steering angle'].to_numpy()
    else:
        steering_angle = model_functions_obj.steering_2_steering_angle(df['steering'].to_numpy(),a_s,b_s,c_s,d_s,e_s)
        df['steering angle'] = steering_angle


    df['Vx_wheel_front'] =  np.cos(-steering_angle) * df['vx body'].to_numpy() - np.sin(-steering_angle)*(df['vy body'].to_numpy() + lf*df['w'].to_numpy())
    
    # evaluate slip angles
    a_slip_f, a_slip_r = model_functions_obj.evaluate_slip_angles(df['vx body'].to_numpy(),df['vy body'].to_numpy(),df['w'].to_numpy(),lf,lr,steering_angle)

    # add new columns
    df['slip angle front'] = a_slip_f
    df['slip angle rear'] = a_slip_r





    # produce data that will be fed into the model

    # since now the steering angle is not necessarily fixed, it is a good idea to apply the first order filter to it, to recover the true steering angle




    # -----     DYNAMICS      ------
    # evaluate forces in body frame starting from the ones in the absolute frame
    Fx_wheel_vec = np.zeros(df.shape[0])
    Fy_r_wheel_vec = np.zeros(df.shape[0])
    Fy_f_wheel_vec = np.zeros(df.shape[0])

    # evalauting lateral velocities on wheels
    V_y_f_wheel = np.zeros(df.shape[0])

    # TESTING
    #l_tilde = -0.5*lf**2-0.5*lr**2-lf*lr
    #l_star = (lf-lr)/2
    #z_COM = 0.07 #  

    #k_pitch_front = z_COM * (+lf + l_star)/l_tilde  / 9.81 # covert to Kg force
    #k_pitch_rear =  z_COM * (-lr + l_star)/l_tilde  / 9.81 # covert to Kg force

    # evaluate lateral forces from lateral and yaw dynamics
    for i in range(0,df.shape[0]):
        # evaluate the centrifugal force 
        #F_cent = - m * df['w'].iloc[i] * (df['vx body'].iloc[i]**2+df['vy body'].iloc[i]**2)**0.5

        # TESTING THE EFFECT OF PITCH AND ROLL DYNAMICS
        #m_modifier_front =  -df['ax body'].iloc[i] * k_pitch_front
        #m_modifier_rear =   -df['ax body'].iloc[i] * k_pitch_rear
        #m_equivalent = m #+ m_modifier_front + m_modifier_rear

        # ax body no centrifugal are just the forces rotated by the yaw angle
        b = np.array([df['ax body no centrifugal'].iloc[i]*m,
                      df['ay body no centrifugal'].iloc[i]*m,
                     (df['acc_w'].iloc[i])*Jz]) 
        
        # use the raw steering angle
        #steer_angle = df['steering angle time delayed'].iloc[i]
        steer_angle = df['steering angle'].iloc[i]
        
        # accounting for static load partitioning on Fx
        c_front = (m_front_wheel)/(m)
        c_rear = (m_rear_wheel)/m

        A = np.array([[+c_front * np.cos(steer_angle) + c_rear * 1,-np.sin(steer_angle)     , 0],
                      [+c_front * np.sin(steer_angle)             ,+np.cos(steer_angle)     , 1],
                      [+c_front * lf * np.sin(steer_angle)        , lf * np.cos(steer_angle),-lr]])
        
        [Fx_i_wheel, Fy_f_wheel, Fy_r_wheel] = np.linalg.solve(A, b)

        Fx_wheel_vec[i]   = Fx_i_wheel
        Fy_f_wheel_vec[i] = Fy_f_wheel
        Fy_r_wheel_vec[i] = Fy_r_wheel
        

        # evaluate wheel lateral velocities
        V_y_f_wheel[i] = np.cos(steer_angle)*(df['vy body'].to_numpy()[i] + lf*df['w'].to_numpy()[i]) - np.sin(steer_angle) * df['vx body'].to_numpy()[i]
    V_y_r_wheel = df['vy body'].to_numpy() - lr*df['w'].to_numpy()

    # add new columns
    df['Fx wheel'] = Fx_wheel_vec  # this is the force on a single wheel
    df['Fy front wheel'] = Fy_f_wheel_vec
    df['Fy rear wheel'] = Fy_r_wheel_vec
    df['V_y front wheel'] = V_y_f_wheel
    df['V_y rear wheel'] = V_y_r_wheel

    return df


def unwrap_hm(x):  # this function is used to unwrap the angles
    if isinstance(x, (int, float)):
        return np.unwrap([x])[0]
    elif isinstance(x, np.ndarray):
        return np.unwrap(x)
    else:
        raise ValueError("Invalid input type. Expected 'float', 'int', or 'numpy.ndarray'.")



# def generate_tensor_past_actions(df, n_past_actions,refinement_factor,key_to_repeat):
#     # due to numerical errors in evauating the convolution integral we need a finer resolution for the time step
#     df_past_action = pd.DataFrame()
#     df_past_action[key_to_repeat] = df[key_to_repeat]
    
#     # Add delayed steering signals based on user input
#     for i in range(0, n_past_actions):
#         df_past_action[key_to_repeat + f' prev{i}'] = df[key_to_repeat].shift(i, fill_value=0)
#     # doing a zero order hold on the steering signal to get  a finer resolution
#     df_past_action_refined = pd.DataFrame()
#     for i in range(0, (n_past_actions)):
#         for k in range(refinement_factor):
#             df_past_action_refined[key_to_repeat + f' prev{i*refinement_factor+k}'] = df_past_action[key_to_repeat + f' prev{i}']


#     # Select columns for generating tensor

#     selected_columns_df = [key_to_repeat + f' prev{i}' for i in range(0, (n_past_actions)*refinement_factor)]
    
#     # Convert the selected columns into a tensor and send to GPU (if available)
#     train_x = torch.tensor(df_past_action_refined[selected_columns_df].to_numpy()).cuda()

#     return train_x

def generate_tensor_past_actions(df, n_past_actions, refinement_factor, key_to_repeat):
    # Initialize a list to store the refined past action values
    refined_past_actions = []
    
    # Iterate over the past actions and create the refined past actions directly
    for i in range(0, n_past_actions):
        # Shift the values for each past action step
        past_action = df[key_to_repeat].shift(i, fill_value=0)
        
        # Refine the action values by zero-order hold and append them to the refined list
        for k in range(refinement_factor):
            refined_past_actions.append(past_action)

    # Convert the refined past actions list into a numpy array (or tensor)
    refined_past_actions_matrix = np.stack(refined_past_actions, axis=1)
    
    # Convert the matrix into a tensor and move it to the GPU (if available)
    train_x = torch.tensor(refined_past_actions_matrix).cuda()

    return train_x




def plot_vicon_data(df):

    # plot vicon data filtering process
    plotting_time_vec = df['vicon time'].to_numpy()

    fig1, ((ax1, ax2, ax3),(ax4, ax5, ax6)) = plt.subplots(2, 3, figsize=(10, 6), constrained_layout=True)
    ax1.set_title('velocity x')
    #ax1.plot(plotting_time_vec, df['vx_abs_raw'].to_numpy(), label="vicon abs vx raw", color='k')
    ax1.plot(plotting_time_vec, df['vx_abs_filtered'].to_numpy(), label="vicon abs vx filtered", color='dodgerblue')
    ax1.legend()

    ax4.set_title('acceleration x')
    #ax4.plot(plotting_time_vec, df['ax_abs_raw'].to_numpy(), label="vicon abs ax raw", color='k')
    #ax4.plot(plotting_time_vec, df['ax_abs_filtered'].to_numpy(), label="vicon abs ax filtered", color='k')
    ax4.plot(plotting_time_vec, df['ax_abs_filtered_more'].to_numpy(), label="vicon abs ax filtered more", color='dodgerblue')
    ax4.legend()


    ax2.set_title('velocity y')
    #ax2.plot(plotting_time_vec, df['vy_abs_raw'].to_numpy(), label="vicon abs vy raw", color='k')
    ax2.plot(plotting_time_vec, df['vy_abs_filtered'].to_numpy(), label="vicon abs vy filtered", color='orangered')
    ax2.legend()

    ax5.set_title('acceleration y')
    #ax5.plot(plotting_time_vec, df['ay_abs_raw'].to_numpy(), label="vicon abs ay raw", color='k')
    #ax5.plot(plotting_time_vec, df['ay_abs_filtered'].to_numpy(), label="vicon abs ay filtered", color='k')
    ax5.plot(plotting_time_vec, df['ay_abs_filtered_more'].to_numpy(), label="vicon abs ay filtered more", color='orangered')
    ax5.legend()


    ax3.set_title('velocity yaw')
    #ax3.plot(plotting_time_vec, df['w_abs_raw'].to_numpy(), label="vicon w raw", color='k')
    ax3.plot(plotting_time_vec, df['w'].to_numpy(), label="vicon w filtered", color='slateblue')
    ax3.legend()

    ax6.set_title('acceleration yaw')
    #ax6.plot(plotting_time_vec, df['aw_abs_raw'].to_numpy(), label="vicon aw raw", color='k')
    #ax6.plot(plotting_time_vec, df['aw_abs_filtered'].to_numpy(), label="vicon aw filtered", color='k')
    ax6.plot(plotting_time_vec, df['acc_w'].to_numpy(), label="vicon aw filtered more", color='slateblue')
    ax6.legend()





    # plot raw opti data
    fig1, ((ax1, ax2, ax3 , ax4)) = plt.subplots(4, 1, figsize=(10, 6), constrained_layout=True)
    ax1.set_title('Velocity data')
    #ax1.plot(plotting_time_vec, df['vx_abs'].to_numpy(), label="Vx abs data", color='lightblue')
    #ax1.plot(plotting_time_vec, df['vy_abs'].to_numpy(), label="Vy abs data", color='rosybrown')
    ax1.plot(plotting_time_vec, df['vx body'].to_numpy(), label="Vx body", color='dodgerblue')
    ax1.plot(plotting_time_vec, df['vy body'].to_numpy(), label="Vy body", color='orangered')
    ax1.legend()

    # plot body frame data time history
    ax2.set_title('Vy data raw vicon')
    ax2.plot(plotting_time_vec, df['throttle'].to_numpy(), label="Throttle",color='gray', alpha=1)
    ax2.plot(plotting_time_vec, df['vel encoder'].to_numpy(),label="Velocity Encoder raw", color='indigo')
    ax2.plot(plotting_time_vec, df['vx body'].to_numpy(), label="Vx body frame",color='dodgerblue')
    ax2.plot(plotting_time_vec, df['Vx_wheel_front'].to_numpy(), label="Vx front wheel",color='navy')
    #ax2.plot(plotting_time_vec, df['vy body'].to_numpy(), label="Vy body frame",color='orangered')
    
    ax2.legend()
    # plot omega data time history
    ax3.set_title('Omega data time history')
    ax3.plot(plotting_time_vec, df['steering'].to_numpy(),label="steering input raw data", color='pink') #  -17 / 180 * np.pi * 
    ax3.plot(plotting_time_vec, df['W (IMU)'].to_numpy(),label="omega IMU raw data", color='orchid')
    #ax3.plot(plotting_time_vec, df['w_abs'].to_numpy(), label="omega opti", color='lightblue')
    ax3.plot(plotting_time_vec, df['w'].to_numpy(), label="omega opti filtered",color='slateblue')
    ax3.legend()

    ax4.set_title('x - y - theta time history')
    ax4.plot(plotting_time_vec, df['vicon x'].to_numpy(), label="x opti",color='slateblue')
    ax4.plot(plotting_time_vec, df['vicon y'].to_numpy(), label="y opti",color='orangered')
    ax4.plot(plotting_time_vec, df['unwrapped yaw'].to_numpy(), label="unwrapped theta",color='yellowgreen')
    ax4.plot(plotting_time_vec, df['vicon yaw'].to_numpy(), label="theta raw data", color='darkgreen')
    ax4.legend()



    # plot slip angles
    fig2, ((ax1, ax2, ax3)) = plt.subplots(3, 1, figsize=(10, 6), constrained_layout=True)
    ax1.set_title('slip angle front')
    ax1.plot(plotting_time_vec, df['slip angle front'].to_numpy(), label="slip angle front", color='peru')
    ax1.plot(plotting_time_vec, df['slip angle rear'].to_numpy(), label="slip angle rear", color='darkred')
    # ax1.plot(plotting_time_vec, df['acc_w'].to_numpy(), label="acc w", color='slateblue')
    # ax1.plot(plotting_time_vec, df['vy body'].to_numpy(), label="Vy body", color='orangered')
    # ax1.plot(plotting_time_vec, df['vx body'].to_numpy(), label="Vx body", color='dodgerblue')
    ax1.legend()

    ax2.set_title('Wheel lateral velocities')
    ax2.plot(plotting_time_vec, df['V_y front wheel'].to_numpy(), label="V_y rear wheel", color='peru')
    ax2.plot(plotting_time_vec, df['V_y rear wheel'].to_numpy(), label="V_y front wheel", color='darkred')
    ax2.legend()


    ax3.set_title('Normalized Steering and acc W')
    ax3.plot(plotting_time_vec, df['acc_w'].to_numpy()/df['acc_w'].max(), label="acc w normalized", color='slateblue')
    ax3.plot(plotting_time_vec, df['steering'].to_numpy()/df['steering'].max(), label="steering normalized", color='purple')
    #ax3.plot(df['vicon time'].to_numpy(),df['steering angle time delayed'].to_numpy()/df['steering angle time delayed'].max(),label='steering angle time delayed normalized',color='k')
    ax3.legend()

    # # plot input data points
    # fig1, ((ax1, ax2)) = plt.subplots(1, 2, figsize=(10, 6), constrained_layout=True)
    # ax1.set_title('control input map')
    # ax1.scatter(df['steering'].to_numpy(), df['throttle'].to_numpy(),color='skyblue')
    # ax1.set_xlabel('steering')
    # ax1.set_ylabel('throttle')
    # ax1.set_xlim([-1,1])

    # ax2.set_title('Vy-Vx map')
    # ax2.scatter(df['vy body'].to_numpy(), df['vx body'].to_numpy(),color='k')
    # ax2.set_xlabel('Vy')
    # ax2.set_ylabel('Vx')

    # # plot Wheel velocity vs force data
    # fig1, ((ax_wheel_f,ax_wheel_r)) = plt.subplots(1, 2, figsize=(10, 6), constrained_layout=True)
    # # determine x limits
    # x_lim = [np.min([df['V_y rear wheel'].min(),df['V_y front wheel'].min()]),
    #          np.max([df['V_y rear wheel'].max(),df['V_y front wheel'].max()])]
    
    # color_code_label = 'ax body'
    # #color_code_label = 'steering angle'
    # #color_code_label = 'ay body no centrifugal'
    # #color_code_label = 'vx body'
    # #color_code_label = 'Fx wheel'
    # c_front = df[color_code_label].to_numpy()
    # #c_front = df[color_code_label].to_numpy()
    # #c_front = (df['Fx wheel'].to_numpy()**2+df['Fy front wheel'].to_numpy()**2) ** 0.5
    # #c_rear = (df['Fx wheel'].to_numpy()**2+df['Fy rear wheel'].to_numpy()**2) ** 0.5
    # #color_code_label = 'total force'

    # ax_wheel_f.scatter(df['V_y front wheel'].to_numpy(),df['Fy front wheel'].to_numpy(),label='front wheel',color='peru',s=3) #df['steering angle time delayed'].diff().to_numpy()
    # scatter_front = ax_wheel_f.scatter(df['V_y front wheel'].to_numpy(),df['Fy front wheel'].to_numpy(),label='front wheel',c=c_front,cmap='plasma',s=3) #df['vel encoder'].to_numpy()- 
    # #ax_wheel_f.scatter(df['V_y rear wheel'].to_numpy(),df['Fy rear wheel'].to_numpy(),label='rear wheel',color='darkred',s=3)
    
    # #scatter = ax_wheel_f.scatter(df['V_y front wheel'].to_numpy(),df['Fy front wheel'].to_numpy(),label='front wheel',s=3,c=df['vicon time'].to_numpy(),  # color coded by 'steering angle time delayed'
    # #cmap='viridis')
    # cbar1 = fig1.colorbar(scatter_front, ax=ax_wheel_f)
    # cbar1.set_label(color_code_label)  # Label the colorbar  'vel encoder-vx body'

    # #ax_wheel_f.scatter(df['V_y rear wheel'].to_numpy(),df['Fy rear wheel'].to_numpy(),label='rear wheel',color='darkred',s=3)
    # scatter_rear = ax_wheel_r.scatter(df['V_y rear wheel'].to_numpy(),df['Fy rear wheel'].to_numpy(),label='rear wheel',c=c_front,cmap='plasma',s=3)
    # #cbar2 = fig1.colorbar(scatter_rear, ax=ax_wheel_f)
    # #cbar2.set_label('ax body')  # Label the colorbar
    # ax_wheel_f.scatter(np.array([0.0]),np.array([0.0]),color='orangered',label='zero',marker='+', zorder=20) # plot zero as an x 
    # #ax_wheel_r.scatter(np.array([0.0]),np.array([0.0]),color='orangered',label='zero',marker='+', zorder=20) # plot zero as an x

    # ax_wheel_r.set_xlabel('V_y wheel')
    # ax_wheel_r.set_ylabel('Fy')
    # ax_wheel_r.set_xlim(x_lim[0],x_lim[1])
    # ax_wheel_r.legend()


    # ax_wheel_f.set_xlabel('V_y wheel')
    # ax_wheel_f.set_ylabel('Fy')
    # ax_wheel_f.set_xlim(x_lim[0],x_lim[1])
    # ax_wheel_f.legend()
    # ax_wheel_f.set_title('Wheel lateral forces')
    # #colorbar = fig1.colorbar(scatter, label='steering angle time delayed derivative')
 
    # get dirctly measurable parameters
    [theta_correction, l_COM, l_lateral_shift_reference ,lr, lf, Jz, m,m_front_wheel,m_rear_wheel] = directly_measured_model_parameters()
    # plot wheel curve
    [a_m, b_m, c_m, d_m,
    a_f, b_f, c_f, d_f,
    a_s, b_s, c_s, d_s, e_s,
    d_t_f, c_t_f, b_t_f,d_t_r, c_t_r, b_t_r,
    a_stfr, b_stfr,d_stfr,e_stfr,f_stfr,g_stfr,
    max_st_dot,fixed_delay_stdn,k_stdn,
    w_natural_Hz_pitch,k_f_pitch,k_r_pitch,
    w_natural_Hz_roll,k_f_roll,k_r_roll]= model_parameters()

    model_functions_obj = model_functions() # instantiate the model functions object





    # plot Wheel velocity vs force data
    fig1, ((ax_wheel_f_alpha,ax_wheel_r_alpha)) = plt.subplots(1, 2, figsize=(10, 6), constrained_layout=True)
    # determine x limits
    x_lim_alpha = [np.min([df['slip angle rear'].min(),df['slip angle front'].min()]),
             np.max([df['slip angle rear'].max(),df['slip angle front'].max()])]
    
    # evaluate wheel curve
    slip_angles_to_plot = np.linspace(x_lim_alpha[0],x_lim_alpha[1],100)
    wheel_curve_f = model_functions_obj.lateral_tire_force(slip_angles_to_plot,d_t_f,c_t_f,b_t_f,m_front_wheel)
    wheel_curve_r = model_functions_obj.lateral_tire_force(slip_angles_to_plot,d_t_r,c_t_r,b_t_r,m_rear_wheel)

    
    y_lim_alpha = [np.min([df['Fy front wheel'].min(),df['Fy rear wheel'].min()]),
                   np.max([df['Fy front wheel'].max(),df['Fy rear wheel'].max()])]
    
    #color_code_label = 'steering'
    color_code_label = 'ax body'
    #color_code_label = 'ay body'
    cmap = 'Spectral'
    #cmap = 'plasma'

    c_front = df[color_code_label].to_numpy()

    scatter_front = ax_wheel_f_alpha.scatter(df['slip angle front'].to_numpy(),df['Fy front wheel'].to_numpy(),label='front wheel',c=c_front,cmap=cmap,s=3) #df['vel encoder'].to_numpy()- 

    cbar1 = fig1.colorbar(scatter_front, ax=ax_wheel_f_alpha)
    cbar1.set_label(color_code_label)  # Label the colorbar  'vel encoder-vx body'

    #ax_wheel_f.scatter(df['V_y rear wheel'].to_numpy(),df['Fy rear wheel'].to_numpy(),label='rear wheel',color='darkred',s=3)
    scatter_rear = ax_wheel_r_alpha.scatter(df['slip angle rear'].to_numpy(),df['Fy rear wheel'].to_numpy(),label='rear wheel',c=c_front,cmap=cmap,s=3)

    #add wheel curve
    ax_wheel_f_alpha.plot(slip_angles_to_plot,wheel_curve_f,color='silver',label='Tire model',linewidth=4,linestyle='--')
    ax_wheel_r_alpha.plot(slip_angles_to_plot,wheel_curve_r,color='silver',label='Tire model',linewidth=4,linestyle='--')


    ax_wheel_f_alpha.scatter(np.array([0.0]),np.array([0.0]),color='orangered',label='zero',marker='+', zorder=20) # plot zero as an x 
    ax_wheel_r_alpha.scatter(np.array([0.0]),np.array([0.0]),color='orangered',label='zero',marker='+', zorder=20) # plot zero as an x

    ax_wheel_r_alpha.set_xlabel('slip angle [rad]')
    ax_wheel_r_alpha.set_ylabel('Fy')
    ax_wheel_r_alpha.set_xlim(x_lim_alpha[0],x_lim_alpha[1])
    ax_wheel_r_alpha.set_ylim(y_lim_alpha[0],y_lim_alpha[1])
    ax_wheel_r_alpha.legend()


    ax_wheel_f_alpha.set_xlabel('slip angle [rad]') 
    ax_wheel_f_alpha.set_ylabel('Fy')
    ax_wheel_f_alpha.set_xlim(x_lim_alpha[0],x_lim_alpha[1])
    ax_wheel_f_alpha.set_ylim(y_lim_alpha[0],y_lim_alpha[1])
    ax_wheel_f_alpha.legend()
    ax_wheel_f_alpha.set_title('Wheel lateral forces')
    #colorbar = fig1.colorbar(scatter, label='steering angle time delayed derivative')
 















    # plot dt data to check no jumps occur
    fig1, ((ax1)) = plt.subplots(1, 1, figsize=(10, 6), constrained_layout=True)
    ax1.plot(df['vicon time'].to_numpy(),df['vicon time'].diff().to_numpy())
    ax1.set_title('time steps')

    # plot acceleration data
    fig1, ((ax1, ax2, ax3),(ax_acc_x_body, ax_acc_y_body, ax_acc_w)) = plt.subplots(2, 3, figsize=(10, 6), constrained_layout=True)
    ax1.plot(df['vicon time'].to_numpy(), df['ax body no centrifugal'].to_numpy(),label='acc x absolute measured in body frame',color = 'dodgerblue')
    ax1.set_xlabel('time [s]')
    ax1.set_title('X_ddot @ R(yaw)')
    ax1.legend()

    ax2.plot(df['vicon time'].to_numpy(), df['ay body no centrifugal'].to_numpy(),label='acc y absolute measured in body frame',color = 'orangered')
    ax2.set_xlabel('time [s]')
    ax2.set_title('Y_ddot @ R(yaw)')
    ax2.legend()

    ax3.plot(df['vicon time'].to_numpy(), df['acc_w'].to_numpy(),label='dt',color = 'slateblue')
    ax3.set_xlabel('time [s]')
    ax3.set_title('Acc w')
    ax3.legend()

    # plot accelerations in the body frame
    ax_acc_x_body.plot(df['vicon time'].to_numpy(), df['ax body'].to_numpy(),label='acc x in body frame',color = 'dodgerblue')
    ax_acc_x_body.set_xlabel('time [s]')
    ax_acc_x_body.set_title('X_ddot @ R(yaw) + cent')
    ax_acc_x_body.legend()

    ax_acc_y_body.plot(df['vicon time'].to_numpy(), df['ay body'].to_numpy(),label='acc y in body frame',color = 'orangered')
    ax_acc_y_body.set_xlabel('time [s]')
    ax_acc_y_body.set_title('Y_ddot @ R(yaw) + cent')
    ax_acc_y_body.legend()

    ax_acc_w.plot(df['vicon time'].to_numpy(), df['acc_w'].to_numpy(),label='acc w',color = 'slateblue')
    ax_acc_w.set_xlabel('time [s]')
    ax_acc_w.set_title('Acc w')
    ax_acc_w.legend()




    # plot x-y trajectory
    plt.figure()
    plt.plot(df['vicon x'].to_numpy(),df['vicon y'].to_numpy())
    plt.title('x-y trajectory')

    # plot the steering angle time delayed vs W  Usefull to get the steering delay right
    plt.figure()
    plt.title('steering angle time delayed vs W nomalized')
    plt.plot(df['vicon time'].to_numpy(),df['steering angle'].to_numpy()/df['steering angle'].max(),label='steering angle normalized')
    #plt.plot(df['vicon time'].to_numpy(),df['steering angle time delayed'].to_numpy()/df['steering angle time delayed'].max(),label='steering angle time delayed normalized')
    plt.plot(df['vicon time'].to_numpy(),df['w'].to_numpy()/df['w'].max(),label='w filtered normalized')
    plt.legend()


    #plot wheel force saturation
    # plot acceleration data
    # evaluate total wheel forces abs value
    Fy_f_wheel_abs = (df['Fy front wheel'].to_numpy()**2 + df['Fx wheel'].to_numpy()**2)**0.5
    Fy_r_wheel_abs = (df['Fy rear wheel'].to_numpy()**2 + df['Fx wheel'].to_numpy()**2)**0.5

    wheel_slippage = np.abs(df['vel encoder'].to_numpy() - df['vx body'].to_numpy())

    fig1, ((ax_total_force_front,ax_total_force_rear)) = plt.subplots(2, 1, figsize=(10, 6), constrained_layout=True)
    ax_total_force_front.plot(df['vicon time'].to_numpy(), Fy_f_wheel_abs,label='Total wheel force front',color = 'peru')
    ax_total_force_front.plot(df['vicon time'].to_numpy(), wheel_slippage,label='longitudinal slippage',color = 'gray')
    ax_total_force_front.plot(df['vicon time'].to_numpy(), df['ax body no centrifugal'].to_numpy(),label='longitudinal acceleration',color = 'dodgerblue')
    ax_total_force_front.plot(df['vicon time'].to_numpy(), df['ay body no centrifugal'].to_numpy(),label='lateral acceleration',color = 'orangered')
    ax_total_force_front.set_xlabel('time [s]')
    ax_total_force_front.set_title('Front total wheel force')
    ax_total_force_front.legend()

    ax_total_force_rear.plot(df['vicon time'].to_numpy(), Fy_r_wheel_abs,label='Total wheel force rear',color = 'darkred')
    ax_total_force_rear.plot(df['vicon time'].to_numpy(), wheel_slippage,label='longitudinal slippage',color = 'gray')
    ax_total_force_rear.plot(df['vicon time'].to_numpy(), df['ax body no centrifugal'].to_numpy(),label='longitudinal acceleration',color = 'dodgerblue')
    ax_total_force_rear.plot(df['vicon time'].to_numpy(), df['ay body no centrifugal'].to_numpy(),label='lateral acceleration',color = 'orangered')
    ax_total_force_rear.set_xlabel('time [s]')
    ax_total_force_rear.set_title('Rear total wheel force')
    ax_total_force_rear.legend()

    # plotting forces
    fig1, ((ax_lat_force,ax_long_force)) = plt.subplots(2, 1, figsize=(10, 6), constrained_layout=True)
    accx_cent = + df['vy body'].to_numpy() * df['w'].to_numpy() 
    accy_cent = - df['vx body'].to_numpy() * df['w'].to_numpy() 
    ax_lat_force.plot(df['vicon time'].to_numpy(), df['Fy front wheel'].to_numpy(),label='Fy front measured',color = 'peru')
    ax_lat_force.plot(df['vicon time'].to_numpy(), df['Fy rear wheel'].to_numpy(),label='Fy rear measured',color = 'darkred')
    ax_lat_force.plot(df['vicon time'].to_numpy(), wheel_slippage,label='longitudinal slippage',color = 'gray')
    ax_lat_force.plot(df['vicon time'].to_numpy(), accx_cent + df['ax body no centrifugal'].to_numpy(),label='longitudinal acceleration (with cent))',color = 'dodgerblue')
    ax_lat_force.plot(df['vicon time'].to_numpy(), accy_cent + df['ay body no centrifugal'].to_numpy(),label='lateral acceleration (with cent)',color = 'orangered')
    ax_lat_force.set_xlabel('time [s]')
    ax_lat_force.set_title('Lateral wheel forces')
    ax_lat_force.legend()

    ax_long_force.plot(df['vicon time'].to_numpy(), df['Fx wheel'].to_numpy(),label='longitudinal forces',color = 'dodgerblue')
    ax_long_force.plot(df['vicon time'].to_numpy(), wheel_slippage,label='longitudinal slippage',color = 'gray')
    ax_long_force.set_xlabel('time [s]')
    ax_long_force.set_title('Longitudinal wheel force')
    ax_long_force.legend()



    return ax_wheel_f_alpha,ax_wheel_r_alpha,ax_total_force_front,\
ax_total_force_rear,ax_lat_force,ax_long_force,\
ax_acc_x_body,ax_acc_y_body,ax_acc_w





class model_functions():
    def __init__(self):
        # this is just a class to collect all the functions that are used to model the dynamics
        pass



    def steering_2_steering_angle(self,steering_command,a_s,b_s,c_s,d_s,e_s):

        if torch.is_tensor(steering_command):
            w_s = 0.5 * (torch.tanh(30*(steering_command+c_s))+1)
            steering_angle1 = b_s * torch.tanh(a_s * (steering_command + c_s)) 
            steering_angle2 = d_s * torch.tanh(e_s * (steering_command + c_s))
            steering_angle = (w_s)*steering_angle1+(1-w_s)*steering_angle2 
        else: # use numpy implementation
            w_s = 0.5 * (np.tanh(30*(steering_command+c_s))+1)
            steering_angle1 = b_s * np.tanh(a_s * (steering_command + c_s))
            steering_angle2 = d_s * np.tanh(e_s * (steering_command + c_s))
            steering_angle = (w_s)*steering_angle1+(1-w_s)*steering_angle2
        return steering_angle
    
    def rolling_friction(self,vx,a_f,b_f,c_f,d_f):
        if torch.is_tensor(vx):
            F_rolling = - ( a_f * torch.tanh(b_f  * vx) + c_f * vx + d_f * vx**2 )
        else:
            F_rolling = - ( a_f * np.tanh(b_f  * vx) + c_f * vx + d_f * vx**2 )
        return F_rolling
    
    def throttle_dynamics(self,throttle,throttle_prev,d_m):
        # NOTE for some reasoon trying to re-order the past throttle actions all at the end makes a big mess for some reason.
        # So ok not clean but this way it works so let's not irritate the coding gods.

        # Generate the k coefficients for past actions
        n_previous_throttle = throttle_prev.shape[1]

        # Generate the k coefficients for past actions
        k_values = [d_m * (1 - d_m)**i for i in range(self.n_previous_throttle + 1)]
        
        # # Calculate sum of k coefficients
        k_sum = sum(k_values)
        
        # Convert the k coefficients (excluding k0) to a tensor and reshape for matrix multiplication
        k_vec = torch.unsqueeze(torch.tensor(k_values[1:], dtype=torch.float64)[:self.n_previous_throttle], 1).cuda()
        
        # Compute filtered throttle signal
        throttle_filtered = (k_values[0] * throttle + throttle_prev @ k_vec) / k_sum

        return throttle_filtered
    
    def motor_force(self,throttle_filtered,v,a_m,b_m,c_m):
        if torch.is_tensor(throttle_filtered):
            w_m = 0.5 * (torch.tanh(100*(throttle_filtered+c_m))+1)
            Fx =  (a_m - b_m * v) * w_m * (throttle_filtered+c_m)
        else:
            w_m = 0.5 * (np.tanh(100*(throttle_filtered+c_m))+1)
            Fx =  (a_m - b_m * v) * w_m * (throttle_filtered+c_m)
        return Fx
    
    def evaluate_slip_angles(self,vx,vy,w,lf,lr,steer_angle):
        vy_wheel_f,vy_wheel_r = self.evalaute_wheel_lateral_velocities(vx,vy,w,steer_angle,lf,lr)

        if torch.is_tensor(vx):
            steer_angle_tensor = steer_angle * torch.Tensor([1]).cuda()
            vx_wheel_f = torch.cos(-steer_angle_tensor) * vx - torch.sin(-steer_angle_tensor)*(vy + lf*w)
            #vy_wheel_f = torch.sin(-steer_angle_tensor) * vx + torch.cos(-steer_angle_tensor)*(vy + lf*w)

            #Vx_correction_term = 0.1*np.exp(-100*vx**2) # keeps it positive and avoids division by zero
            Vx_correction_term_f = 1 * torch.exp(-3*vx_wheel_f**2)
            Vx_correction_term_r = 1 * torch.exp(-3*vx**2)
            #Vx_correction_term = 0.5 * torch.exp(-3*vx**2)

            Vx_f = vx_wheel_f + Vx_correction_term_f
            Vx_r = vx + Vx_correction_term_r
            #Vx = vx + Vx_correction_term

            # evaluate slip angles
            alpha_f = torch.atan2(vy_wheel_f, Vx_f) #- steer_angle * (0.5 * (1+torch.tan(50*(vx-0.2))))
            alpha_r = torch.atan2(vy_wheel_r, Vx_r)
        else:
            # do the same but for numpy
            vx_wheel_f = np.cos(-steer_angle) * vx - np.sin(-steer_angle)*(vy + lf*w)
            #vy_wheel_f = np.sin(-steer_angle) * vx + np.cos(-steer_angle)*(vy + lf*w)

            #Vx_correction_term = 0.1*np.exp(-100*vx**2) # keeps it positive and avoids division by zero
            Vx_correction_term_f = 1 * np.exp(-3*vx_wheel_f**2) # 0.5 * (1+np.tanh(-vx_wheel_f*2)) 
            Vx_correction_term_r = 1 * np.exp(-3*vx**2) # 0.5 * (1+np.tanh(-vx*2)) 
            #Vx_correction_term = 0.5 * np.exp(-10*vx**2)

            Vx_f = vx_wheel_f + Vx_correction_term_f
            Vx_r = vx + Vx_correction_term_r
            
            #Vx = vx + Vx_correction_term
            # evaluate slip angles
            alpha_f = np.arctan2(vy_wheel_f,Vx_f)
            alpha_r = np.arctan2(vy_wheel_r,Vx_r)
            
        return alpha_f,alpha_r
    
    def lateral_forces_activation_term(self,vx):
        if torch.is_tensor(vx):
            return torch.tanh(100 * vx**2)
        else:
            return np.tanh(100 * vx**2)


    def lateral_tire_force(self,alpha,d_t,c_t,b_t,m_wheel):
        if torch.is_tensor(alpha):
            F_y = m_wheel * 9.81 * d_t * torch.sin(c_t * torch.arctan(b_t * alpha)) 
        else:
            F_y = m_wheel * 9.81 * d_t * np.sin(c_t * np.arctan(b_t * alpha))



        # if torch.is_tensor(alpha):
        #     # custom designed function that is a tanh that will then settle at a given slope
        #     w1 = 0.5 * (torch.tanh(200*(alpha-c_t))+1)
        #     w2 = 0.5 * (torch.tanh(200*(-alpha-c_t))+1)

        #     slope_in_c = d_t / (1 + (np.pi/2*d_t*c_t)**2)

        #     offset = torch.arctan(d_t * c_t * np.pi/2*torch.Tensor([1]).cuda()) * 2 / np.pi - c_t * slope_in_c # had to multiply by 1 to make it a tensor

        #     f1 = torch.arctan(d_t * np.pi/2 * alpha) * 2 / np.pi
        #     r1 = alpha * slope_in_c + offset
        #     r2 = alpha * slope_in_c - offset

        #     F_y = m_wheel * 9.81 * b_t * ((1-w1-w2)*f1 + w1 * r1 + w2 * r2)  # account for different veritical loads on the wheels
        # else:
        #     w1 = 0.5 * (np.tanh(200*(alpha-c_t))+1)
        #     w2 = 0.5 * (np.tanh(200*(-alpha-c_t))+1)

        #     slope_in_c = d_t / (1 + (np.pi/2*d_t*c_t)**2)

        #     offset = np.arctan(d_t * c_t * np.pi/2) * 2 / np.pi - c_t * slope_in_c

        #     f1 = np.arctan(d_t * np.pi/2 * alpha) * 2 / np.pi
        #     r1 = alpha * slope_in_c + offset
        #     r2 = alpha * slope_in_c - offset

        #     F_y = m_wheel * 9.81 * b_t * ((1-w1-w2)*f1 + w1 * r1 + w2 * r2)  # account for different veritical loads on the wheels

        return F_y 
    
    def evalaute_wheel_lateral_velocities(self,vx,vy,w,steer_angle,lf,lr):
        if torch.is_tensor(vx):
            Vy_wheel_f = - torch.sin(steer_angle) * vx + torch.cos(steer_angle)*(vy + lf*w) 
            Vy_wheel_r = vy - lr*w
        else:
            Vy_wheel_f = - np.sin(steer_angle) * vx + np.cos(steer_angle)*(vy + lf*w) 
            Vy_wheel_r = vy - lr*w
        return Vy_wheel_f,Vy_wheel_r
    
    def F_friction_due_to_steering(self,steer_angle,vx,a,b,d,e,f,g):        # evaluate forward force
        # vx_term = self.rolling_friction(vx,self.a_f,self.b_f,self.c_f,self.d_f)
        
        if torch.is_tensor(steer_angle):
            w_friction_term = 0.5 * (torch.tanh(30*(steer_angle))+1)
            friction_term_1 =  a * torch.tanh(b * steer_angle)
            friction_term_2 =  e * torch.tanh(d * steer_angle)
            friction_term = (w_friction_term)*friction_term_1 + (1-w_friction_term)*friction_term_2

            #vx_term = -((0.5 + 0.5 * torch.tanh(20 * vx -3)) * (f + g * vx)) # *  (f * torch.exp(-g*vx) + 1 ) #   #(1 + f * torch.exp(-g * vx**2)) * vx
            vx_term = self.rolling_friction(vx,self.a_f,self.b_f,self.c_f,self.d_f)  *  (f * torch.exp(-g*vx) + 1 )
        
        else:
            if self.a_stfr:
                w_friction_term = 0.5 * (np.tanh(30*(steer_angle))+1)
                friction_term_1 =  a * np.tanh(b * steer_angle)
                friction_term_2 =  e * np.tanh(d * steer_angle)
                friction_term = (w_friction_term)*friction_term_1+(1-w_friction_term)*friction_term_2
                #vx_term = -((0.5 + 0.5 * np.tanh(20 * vx -3)) * (f + g * vx)) #(1 + f * np.exp(-g * vx**2)) * vx
                vx_term = self.rolling_friction(vx,self.a_f,self.b_f,self.c_f,self.d_f)  *  (f * np.exp(-g*vx) + 1 )
            else:
                friction_term = 0
                vx_term = 0

        return  vx_term * friction_term


    
    def solve_rigid_body_dynamics(self,vx,vy,w,steer_angle,Fx_front,Fx_rear,Fy_wheel_f,Fy_wheel_r,lf,lr,m,Jz):
        if torch.is_tensor(vx):
            # evaluate centripetal acceleration
            a_cent_x = + w * vy  # x component of ac_centripetal
            a_cent_y = - w * vx  # y component of ac_centripetal

            # evaluate body forces
            Fx_body =  Fx_front*(torch.cos(steer_angle))+ Fx_rear + Fy_wheel_f * (-torch.sin(steer_angle))

            Fy_body =  Fx_front*(torch.sin(steer_angle)) + Fy_wheel_f * (torch.cos(steer_angle)) + Fy_wheel_r

            M       = Fx_front * (+torch.sin(steer_angle)*lf) + Fy_wheel_f * (torch.cos(steer_angle)*lf)+\
                    Fy_wheel_r * (-lr) 
            
            acc_x = Fx_body/m + a_cent_x
            acc_y = Fy_body/m + a_cent_y
            acc_w = M/Jz
        else:
            # evaluate centripetal acceleration
            a_cent_x = + w * vy
            a_cent_y = - w * vx

            # evaluate body forces
            Fx_body =  Fx_front*(np.cos(steer_angle))+ Fx_rear + Fy_wheel_f * (-np.sin(steer_angle))

            Fy_body =  Fx_front*(np.sin(steer_angle)) + Fy_wheel_f * (np.cos(steer_angle)) + Fy_wheel_r

            M       = Fx_front * (+np.sin(steer_angle)*lf) + Fy_wheel_f * (np.cos(steer_angle)*lf)+\
                    Fy_wheel_r * (-lr)
            
            acc_x = Fx_body/m + a_cent_x
            acc_y = Fy_body/m + a_cent_y
            acc_w = M/Jz
        
        return acc_x,acc_y,acc_w







class steering_curve_model(torch.nn.Sequential,model_functions):
    def __init__(self,initial_guess):
        super(steering_curve_model, self).__init__()
        self.register_parameter(name='a_s', param=torch.nn.Parameter(torch.Tensor(initial_guess[0])))
        self.register_parameter(name='b_s', param=torch.nn.Parameter(torch.Tensor(initial_guess[1])))
        self.register_parameter(name='c_s', param=torch.nn.Parameter(torch.Tensor(initial_guess[2])))
        self.register_parameter(name='d_s', param=torch.nn.Parameter(torch.Tensor(initial_guess[3])))
        self.register_parameter(name='e_s', param=torch.nn.Parameter(torch.Tensor(initial_guess[4])))

    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm
        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1

        a_s = self.minmax_scale_hm(0.1,5,constraint_weights(self.a_s))
        b_s = self.minmax_scale_hm(0.2,0.6,constraint_weights(self.b_s))
        c_s = self.minmax_scale_hm(-0.1,0.1,constraint_weights(self.c_s))

        d_s = self.minmax_scale_hm(0.2,0.6,constraint_weights(self.d_s))
        e_s = self.minmax_scale_hm(0.1,5,constraint_weights(self.e_s))
        return [a_s,b_s,c_s,d_s,e_s]
        
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)

    def forward(self, steering_command):
        [a_s,b_s,c_s,d_s,e_s] = self.transform_parameters_norm_2_real()
        steering_angle = self.steering_2_steering_angle(steering_command,a_s,b_s,c_s,d_s,e_s)
        return steering_angle
    



class steering_actuator_model(torch.nn.Sequential):
    def __init__(self):
        super(steering_actuator_model, self).__init__()
        self.register_parameter(name='k', param=torch.nn.Parameter(torch.Tensor([10.0])))

    
    def forward(self, train_x):  # this is the model that will be fitted
        # extract data
        steering_angle_reference = train_x[:,0]
        steering_angle = train_x[:,1]
        # evalaute output
        steer_angle_dot = self.k * (steering_angle_reference - steering_angle)

        return steer_angle_dot
    







class friction_curve_model(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals):
        super(friction_curve_model, self).__init__()
        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        self.register_parameter(name='a', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b', param=torch.nn.Parameter(torch.Tensor([param_vals[1]]).cuda()))
        self.register_parameter(name='c', param=torch.nn.Parameter(torch.Tensor([param_vals[2]]).cuda()))
        self.register_parameter(name='d', param=torch.nn.Parameter(torch.Tensor([param_vals[3]]).cuda()))


    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm

        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1

        #friction curve = -  a * tanh(b  * v) - v * c
        a = self.minmax_scale_hm(0.1,3.0,constraint_weights(self.a))
        b = self.minmax_scale_hm(1,100,constraint_weights(self.b))
        c = self.minmax_scale_hm(0.01,2,constraint_weights(self.c))
        d = self.minmax_scale_hm(-0.2,0.2,constraint_weights(self.d))
        return [a,b,c,d]
  
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    
    def forward(self, train_x):  # this is the model that will be fitted
        # --- friction evalaution
        [a,b,c,d] = self.transform_parameters_norm_2_real()
        return self.rolling_friction(train_x,a,b,c,d)


class motor_curve_model(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals,n_previous_throttle):
        super(motor_curve_model, self).__init__()
        # define number of past throttle actions to keep use
        self.n_previous_throttle = n_previous_throttle


        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        self.register_parameter(name='a', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b', param=torch.nn.Parameter(torch.Tensor([param_vals[1]]).cuda()))
        self.register_parameter(name='c', param=torch.nn.Parameter(torch.Tensor([param_vals[2]]).cuda()))
        self.register_parameter(name='d', param=torch.nn.Parameter(torch.Tensor([param_vals[3]]).cuda()))


    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm
        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1

        # motor curve F= (a - v * b) * w * (throttle+c) : w = 0.5 * (torch.tanh(100*(throttle+c))+1)
        a = self.minmax_scale_hm(0,45,constraint_weights(self.a))
        b = self.minmax_scale_hm(0,15,constraint_weights(self.b))
        c = self.minmax_scale_hm(-0.3,0,constraint_weights(self.c))
        d = self.minmax_scale_hm(0,1,constraint_weights(self.d))


        return [a,b,c,d]
        
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    
    def forward(self, train_x):  # this is the model that will be fitted
        throttle = torch.unsqueeze(train_x[:,0],1)
        v = torch.unsqueeze(train_x[:,1],1)
        #throttle_prev = torch.unsqueeze(train_x[:,2],1)
        #throttle_prev_prev = torch.unsqueeze(train_x[:,3],1)
        throttle_prev = train_x[:,2:2+self.n_previous_throttle]

        # evaluate motor force as a function of the throttle
        [a,b,c,d] = self.transform_parameters_norm_2_real()
        # evaluate coefficients for the throttle filter
        k0 = d
        k1 = d * (1-d)
        k2 = d * (1-d)**2
        k3 = d * (1-d)**3 
        k4 = d * (1-d)**4 
        k5 = d * (1-d)**5 
        sum = (k0+k1+k2+k3+k4+k5)

        k_vec = torch.unsqueeze(torch.cat([k1,k2,k3,k4,k5],0)[:self.n_previous_throttle],1).double()

        throttle_filtered = (k0 * throttle + throttle_prev @ k_vec)/sum

        Fx = self.motor_force(throttle_filtered,v,a,b,c)

        return Fx
    




class motor_and_friction_model(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals,n_previous_throttle):
        super(motor_and_friction_model, self).__init__()
        # define number of past throttle actions to keep use
        self.n_previous_throttle = n_previous_throttle


        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        # motor parameters
        self.register_parameter(name='a_m', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_m', param=torch.nn.Parameter(torch.Tensor([param_vals[1]]).cuda()))
        self.register_parameter(name='c_m', param=torch.nn.Parameter(torch.Tensor([param_vals[2]]).cuda()))
        self.register_parameter(name='d_m', param=torch.nn.Parameter(torch.Tensor([param_vals[3]]).cuda()))
        # friction parameters
        self.register_parameter(name='a_f', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_f', param=torch.nn.Parameter(torch.Tensor([param_vals[1]]).cuda()))
        self.register_parameter(name='c_f', param=torch.nn.Parameter(torch.Tensor([param_vals[2]]).cuda()))
        self.register_parameter(name='d_f', param=torch.nn.Parameter(torch.Tensor([param_vals[3]]).cuda()))

    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm
        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1

        # motor curve F= (a - v * b) * w * (throttle+c) : w = 0.5 * (torch.tanh(100*(throttle+c))+1)
        a_m = self.minmax_scale_hm(0,45,constraint_weights(self.a_m))
        b_m = self.minmax_scale_hm(0,15,constraint_weights(self.b_m))
        c_m = self.minmax_scale_hm(-0.3,0,constraint_weights(self.c_m))
        d_m = self.minmax_scale_hm(0,1,constraint_weights(self.d_m))

        # friction curve F= -  a * tanh(b  * v) - v * c
        a_f = self.minmax_scale_hm(0.1,3.0,constraint_weights(self.a_f))
        b_f = self.minmax_scale_hm(1,100,constraint_weights(self.b_f))
        c_f = self.minmax_scale_hm(0.01,2,constraint_weights(self.c_f))
        d_f = self.minmax_scale_hm(-0.2,0.2,constraint_weights(self.d_f))

        return [a_m,b_m,c_m,d_m,a_f,b_f,c_f,d_f]
    
        
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    
    def forward(self, train_x):  # this is the model that will be fitted
        throttle = torch.unsqueeze(train_x[:,0],1)
        v = torch.unsqueeze(train_x[:,1],1)
        #throttle_prev = torch.unsqueeze(train_x[:,2],1)
        #throttle_prev_prev = torch.unsqueeze(train_x[:,3],1)
        throttle_prev = train_x[:,2:2+self.n_previous_throttle]

        # evaluate motor force as a function of the throttle
        [a_m,b_m,c_m,d_m,a_f,b_f,c_f,d_f] = self.transform_parameters_norm_2_real()

        throttle_filtered = self.throttle_dynamics(throttle,throttle_prev,d_m)
        
        Fx = self.motor_force(throttle_filtered,v,a_m,b_m,c_m) + self.rolling_friction(v,a_f,b_f,c_f,d_f)

        return Fx

    





class vicon_parameters_model(torch.nn.Sequential):
    def __init__(self,initial_guess):
        super(vicon_parameters_model, self).__init__()
        self.register_parameter(name='theta_correction', param=torch.nn.Parameter(torch.Tensor(initial_guess[0])))
        self.register_parameter(name='lr', param=torch.nn.Parameter(torch.Tensor(initial_guess[1])))

    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm
        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1

        theta_correction = self.minmax_scale_hm(-0.35,+0.35,constraint_weights(self.theta_correction)) # degrees
        lr = self.minmax_scale_hm(0,0.175,constraint_weights(self.lr))

        return [theta_correction,lr]
    
        
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)

    def forward(self, train_x):
        v_x_abs = torch.unsqueeze(train_x[:,0],1)
        v_y_abs = torch.unsqueeze(train_x[:,1],1)
        theta = torch.unsqueeze(train_x[:,2],1)

        [theta_correction,lr] = self.transform_parameters_norm_2_real()

        # rot angle
        rot_angle = - (theta+theta_correction)

        Vx_body = v_x_abs * torch.cos(rot_angle) - v_y_abs * torch.sin(rot_angle)   
        Vy_body = v_x_abs * torch.sin(rot_angle) + v_y_abs * torch.cos(rot_angle)


        return Vx_body,Vy_body/lr
    








class pacejka_tire_model(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals,m_front_wheel,m_rear_wheel):
        super(pacejka_tire_model, self).__init__()
        # define mass of the robot
        self.m_front_wheel = m_front_wheel
        self.m_rear_wheel = m_rear_wheel

        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        self.register_parameter(name='d_f', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='c_f', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_f', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))


        self.register_parameter(name='d_r', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='c_r', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_r', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))

    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm

        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1
        
        d_f = self.minmax_scale_hm(0,-2,constraint_weights(self.d_f))
        c_f = self.minmax_scale_hm(0,2,constraint_weights(self.c_f))
        b_f = self.minmax_scale_hm(0.01,20,constraint_weights(self.b_f))
        #e_f = self.minmax_scale_hm(-1,1,constraint_weights(self.e_f))

        # rear tire
        d_r = self.minmax_scale_hm(0,-2,constraint_weights(self.d_r))
        c_r = self.minmax_scale_hm(0,2,constraint_weights(self.c_r))
        b_r = self.minmax_scale_hm(0.01,20,constraint_weights(self.b_r))
        #e_r = self.minmax_scale_hm(-1,1,constraint_weights(self.e_r))

        return [d_f,c_f,b_f,d_r,c_r,b_r]
        
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    
    def forward(self, train_x):  # this is the model that will be fitted
        alpha_front = torch.unsqueeze(train_x[:,0],1)
        alpha_rear  = torch.unsqueeze(train_x[:,1],1) 
    
        [d_t_f,c_t_f,b_t_f,d_t_r,c_t_r,b_t_r] = self.transform_parameters_norm_2_real() 
        # evalaute lateral tire force

        F_y_f = self.lateral_tire_force(alpha_front,d_t_f,c_t_f,b_t_f,self.m_front_wheel) # adding front-rear nominal loading
        F_y_r = self.lateral_tire_force(alpha_rear,d_t_r,c_t_r,b_t_r,self.m_rear_wheel) 

        return F_y_f,F_y_r






class pacejka_tire_model_pitch_roll(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals,m_front_wheel,m_rear_wheel,lf,lr,d_t_f,c_t_f,b_t_f,d_t_r,c_t_r,b_t_r):
        super(pacejka_tire_model_pitch_roll, self).__init__()
        # define mass of the robot
        self.m_front_wheel = m_front_wheel
        self.m_rear_wheel = m_rear_wheel
        self.lf = lf
        self.lr = lr
        # save tire parameters
        self.d_t_f = d_t_f
        self.c_t_f = c_t_f
        self.b_t_f = b_t_f

        self.d_t_r = d_t_r
        self.c_t_r = c_t_r
        self.b_t_r = b_t_r



        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        self.register_parameter(name='k_pitch', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='k_roll', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))

    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm

        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1
        
        k_pitch = self.minmax_scale_hm(0,0.1,constraint_weights(self.k_pitch))
        k_roll = self.minmax_scale_hm(-2,2,constraint_weights(self.k_roll))

        return [k_pitch,k_roll]
        
    def minmax_scale_hm(self,min,max,normalized_value):
        # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    
    def forward(self, train_x):  # this is the model that will be fitted
        alpha_front = torch.unsqueeze(train_x[:,0],1)
        alpha_rear  = torch.unsqueeze(train_x[:,1],1)
        acc_x = torch.unsqueeze(train_x[:,2],1)
        acc_y  = torch.unsqueeze(train_x[:,3],1)
    
        [k_pitch,k_roll] = self.transform_parameters_norm_2_real() 

        # TESTING
        l_tilde = -0.5*self.lf**2-0.5*self.lr**2-self.lf*self.lr
        l_star = (self.lf-self.lr)/2
        #z_COM = 0.07 #  

        k_pitch_front = k_pitch * (+self.lf + l_star)/l_tilde  / 9.81 # covert to Kg force
        k_pitch_rear =  k_pitch * (-self.lr + l_star)/l_tilde  / 9.81 # covert to Kg force

        alpha_front_modifier_roll = acc_y * k_roll


        D_m_f = -acc_x * k_pitch_front 
        D_m_r = -acc_x * k_pitch_rear  + k_roll * acc_y

        # evalaute lateral tire force

        F_y_f = self.lateral_tire_force(alpha_front+alpha_front_modifier_roll,self.d_t_f,self.c_t_f,self.b_t_f,self.m_front_wheel) # adding front-rear nominal loading
        F_y_r = self.lateral_tire_force(alpha_rear,self.d_t_r,self.c_t_r,self.b_t_r,self.m_rear_wheel) #+ D_m_r

        return F_y_f,F_y_r










class culomb_pacejka_tire_model_full_dynamics(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals):
        super(culomb_pacejka_tire_model_full_dynamics, self).__init__()
        # define mass of the robot

        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        self.register_parameter(name='Jz', param=torch.nn.Parameter(torch.Tensor([0.006513]).cuda())) # 0.006513
        self.register_parameter(name='lr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))


        self.register_parameter(name='d_t', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='c_t', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_t', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        
        self.register_parameter(name='a_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='d_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='e_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='f_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='g_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))

        [theta_correction, lr, l_COM, Jz, lf, m,
        a_m, b_m, c_m, d_m,
        a_f, b_f, c_f, d_f,
        a_s, b_s, c_s, d_s, e_s,
        d_t, c_t, b_t,
        a_stfr, b_stfr,d_stfr,e_stfr,f_stfr,g_stfr,
        max_st_dot,fixed_delay_stdn,k_stdn,
        w_natural_Hz_pitch,k_f_pitch,k_r_pitch,
        w_natural_Hz_roll,k_f_roll,k_r_roll] = model_parameters()

        self.m = m
        #self.lr = lr
        #self.lf = lf
        #self.Jz = Jz

        # Motor curve
        self.a_m =  a_m
        self.b_m =  b_m
        self.c_m =  c_m

        #Friction curve
        self.a_f =  a_f
        self.b_f =  b_f
        self.c_f =  c_f
        self.d_f =  d_f



    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm

        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1

        #friction curve F= -  a * tanh(b  * v) - v * c
        #friction curve F= -  a * tanh(b  * v) - v * c
        Jz = self.minmax_scale_hm(0,0.01,constraint_weights(self.Jz)) #  20 * 0.006513
        lr = self.minmax_scale_hm(0,0.175,constraint_weights(self.lr)) # 0.175
        d_t = self.minmax_scale_hm(-1,-20,constraint_weights(self.d_t))
        c_t = self.minmax_scale_hm(0.5,1.5,constraint_weights(self.c_t))
        b_t = self.minmax_scale_hm(0.01,10,constraint_weights(self.b_t))
        a_stfr = self.minmax_scale_hm(0,5,constraint_weights(self.a_stfr))
        b_stfr = self.minmax_scale_hm(0,5,constraint_weights(self.b_stfr))
        d_stfr = self.minmax_scale_hm(0,7,constraint_weights(self.d_stfr))
        e_stfr = self.minmax_scale_hm(0,5,constraint_weights(self.e_stfr))
        f_stfr = self.minmax_scale_hm(0.01,20,constraint_weights(self.f_stfr))
        g_stfr = self.minmax_scale_hm(0.01,20,constraint_weights(self.g_stfr))
        return [Jz,lr,d_t,c_t,b_t,a_stfr,b_stfr,d_stfr,e_stfr,f_stfr,g_stfr]
        
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    
    def forward(self, train_x):  # this is the model that will be fitted
        vx = torch.unsqueeze(train_x[:,0],1)
        vy = torch.unsqueeze(train_x[:,1],1) 
        w = torch.unsqueeze(train_x[:,2],1)
        throttle = torch.unsqueeze(train_x[:,3],1)
        steering_angle = torch.unsqueeze(train_x[:,4],1)

        # extract fitting parameters
        [Jz,lr,d_t,c_t,b_t,a_stfr,b_stfr,d_stfr,e_stfr,f_stfr,g_stfr] = self.transform_parameters_norm_2_real()
        lf = 0.175 - lr

        # evaluate longitudinal forces
        Fx = + self.motor_force(throttle,vx,self.a_m,self.b_m,self.c_m) \
             + self.rolling_friction(vx,self.a_f,self.b_f,self.c_f,self.d_f)\
             + self.F_friction_due_to_steering(steering_angle,vx,a_stfr,b_stfr,d_stfr,e_stfr,f_stfr,g_stfr) 
        
        # partition longitudinal forces to front and rear tires according to static weight distribution
        Fx_front = Fx/2 * lr/(lr+lf)
        Fx_rear = Fx/2 * lf/(lr+lf)

        # evaluate lateral tire forces
        Vy_wheel_f,Vy_wheel_r = self.evalaute_wheel_lateral_velocities(vx,vy,w,steering_angle,lf,lr)

        # accounting for static load partitioning
        Fy_wheel_f = self.lateral_tire_force(Vy_wheel_f,d_t,c_t,b_t) * lr/(lr+lf)
        Fy_wheel_r = self.lateral_tire_force(Vy_wheel_r,d_t,c_t,b_t) *  lf/(lr+lf)

        acc_x,acc_y,acc_w = self.solve_rigid_body_dynamics(vx,vy,w,steering_angle,Fx_front,Fx_rear,Fy_wheel_f,Fy_wheel_r,lf,lr,self.m,Jz)


        return acc_x,acc_y,acc_w,Vy_wheel_f,Vy_wheel_r







class steering_dynamics_model(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals,dt,tweak_steering_curve):
        super(steering_dynamics_model, self).__init__()

        # NOTE:
        # if the chosen dynamics are longer than the amount of samples you have, you can in the end subtract energy from the signal,
        # so if you see that the settling point of the new steering command is lower than what you expect, you can increase the number of past actions
        # or give the freedom to change also the steering curve

        self.dt = dt
        self.tweak_steering_curve = tweak_steering_curve
        # get model parameters
        [theta_correction, self.lr, self.l_COM, self.Jz, self.lf, self.m,
        self.a_m, self.b_m, self.c_m, self.d_m,
        self.a_f, self.b_f, self.c_f, self.d_f,
        self.a_s_original, self.b_s_original, self.c_s_original, self.d_s_original,self.e_s_original,
        d_t, c_t, b_t,
        self.a_stfr, self.b_stfr] = model_parameters()

        #define relu for later use
        self.relu = torch.nn.ReLU()

        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        #steering dynamics parameters
        self.register_parameter(name='damping', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='w_natural', param=torch.nn.Parameter(torch.Tensor([param_vals[1]]).cuda()))
        self.register_parameter(name='fixed_delay', param=torch.nn.Parameter(torch.Tensor([param_vals[2]]).cuda()))

        # also tweeaking the steering curve
        self.register_parameter(name='a_s', param=torch.nn.Parameter(torch.Tensor(param_vals[3])))
        self.register_parameter(name='b_s', param=torch.nn.Parameter(torch.Tensor(param_vals[4])))
        self.register_parameter(name='c_s', param=torch.nn.Parameter(torch.Tensor(param_vals[5])))
        self.register_parameter(name='d_s', param=torch.nn.Parameter(torch.Tensor(param_vals[6])))
        self.register_parameter(name='e_s', param=torch.nn.Parameter(torch.Tensor(param_vals[7])))

        


    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm
        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1
        #damping = self.minmax_scale_hm(0.01,0.99,constraint_weights(self.damping)) # this needs to be either in (0,1), 1 or (1,inf]
        damping = self.minmax_scale_hm(0.6,2,constraint_weights(self.damping))
        w_natural = self.minmax_scale_hm(0.1,20,constraint_weights(self.w_natural))
        fixed_delay = self.minmax_scale_hm(0.0,0.2,constraint_weights(self.fixed_delay))

        a_s = self.minmax_scale_hm(1.0,1.5,constraint_weights(self.a_s))
        b_s = self.minmax_scale_hm(0.2,0.6,constraint_weights(self.b_s))
        c_s = self.minmax_scale_hm(-0.1,+0.1,constraint_weights(self.c_s))
        d_s = self.minmax_scale_hm(0.20,0.70,constraint_weights(self.d_s))
        e_s = self.minmax_scale_hm(0.5,1.5,constraint_weights(self.e_s))


        return [damping,w_natural,fixed_delay,a_s,b_s,c_s,d_s,e_s]

    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    

    def produce_past_action_coefficients(self,damping,w_natural,fixed_delay,length):
        # Generate the k coefficients for past actions
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        k_vec = torch.zeros((length,1)).cuda()
        for i in range(length):
            k_vec[i]=self.impulse_response(i*self.dt,damping,w_natural,fixed_delay)
        return k_vec * self.dt  # the dt is really important to get the amplitude right


    def impulse_response(self,t_tilde,damping,w_natural,fixed_delay):
        #second order impulse response
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        w = w_natural * 2 *np.pi # convert to rad/s
        z = damping

        # add fixed time delay
        t = self.relu(t_tilde-fixed_delay)
        #t = (0.5*torch.tanh(50*(t_tilde-fixed_delay))+0.5)*(t_tilde-fixed_delay)

        # different responses for different damping ratios
        if z >1:
            a = torch.sqrt(z**2-1)
            f = w/(2*a) * (torch.exp(-w*(z-a)*t) - torch.exp(-w*(z+a)*t))

        elif z == 1:
            f = w**2 * t * torch.exp(-w*t)

        elif z < 1:
            w_d = w * torch.sqrt(1-z**2)
            f = w/(torch.sqrt(1-z**2))*torch.exp(-z*w*t)*torch.sin(w_d*t)

        return f

    def impulse_response_dev(self,t_tilde,damping,w_natural,fixed_delay):
        #second order impulse response
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        w = w_natural * 2 *np.pi # convert to rad/s
        z = damping

        # add fixed time delay
        t = self.relu(t_tilde-fixed_delay)
        #t = (0.5*torch.tanh(50*(t_tilde-fixed_delay))+0.5)*(t_tilde-fixed_delay)

        # different responses for different damping ratios
        # if z >1:
        #     a = torch.sqrt(z**2-1)
        #     f = w/(2*a) * (torch.exp(-w*(z-a)*t) - torch.exp(-w*(z+a)*t))

        # elif z == 1:
        f = w**2 * (torch.exp(-w*t)-w*t*torch.exp(-w*t))#w**2 * t * torch.exp(-w*t)  

        # elif z < 1:
        #     w_d = w * torch.sqrt(1-z**2)
        #     f = w/(torch.sqrt(1-z**2))*torch.exp(-z*w*t)*torch.sin(w_d*t)

        return f




    def forward(self, train_x):  # this is the model that will be fitted
        # training_x = steering values
 
        [damping,w_natural,fixed_delay,a_s,b_s,c_s,d_s,e_s] = self.transform_parameters_norm_2_real()

        #produce past action coefficients
        length = train_x.shape[1]
        k_vec = self.produce_past_action_coefficients(damping,w_natural,fixed_delay,length).double()

        steering_integrated = train_x @ k_vec


        if self.tweak_steering_curve:
            # w_s = 0.5 * (torch.tanh(30*(steering_integrated+c_s))+1)
            # steering_angle1 = b_s * torch.tanh(a_s * (steering_integrated + c_s)) 
            # steering_angle2 = d_s * torch.tanh(e_s * (steering_integrated + c_s)) 
            # steering_angle = (w_s)*steering_angle1+(1-w_s)*steering_angle2
            steering_angle = self.steering_2_steering_angle(steering_integrated,a_s,b_s,c_s,d_s,e_s)
        else:
            # w_s = 0.5 * (torch.tanh(30*(steering_integrated+self.c_s_original))+1)
            # steering_angle1 = self.b_s_original * torch.tanh(self.a_s_original * (steering_integrated + self.c_s_original)) 
            # steering_angle2 = self.d_s_original * torch.tanh(self.e_s_original * (steering_integrated + self.c_s_original)) 
            # steering_angle = (w_s)*steering_angle1+(1-w_s)*steering_angle2
            steering_angle = self.steering_2_steering_angle(steering_integrated,self.a_s_original,self.b_s_original,self.c_s_original,self.d_s_original,self.e_s_original)

        return steering_angle
    



class pitch_and_roll_dynamics_model(torch.nn.Sequential):
    def __init__(self,param_vals,dt,n_past_actions,lr,lf):
        super(pitch_and_roll_dynamics_model, self).__init__()

        # NOTE:
        # if the chosen dynamics are longer than the amount of samples you have, you can in the end subtract energy from the signal,
        # so if you see that the settling point of the new steering command is lower than what you expect, you can increase the number of past actions
        # or give the freedom to change also the steering curve

        self.dt = dt
        self.n_past_actions = n_past_actions
        self.lr = lr
        self.lf = lf

        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        # pitch_dynamics
        self.register_parameter(name='w_natural_Hz_pitch', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='k_f_pitch', param=torch.nn.Parameter(torch.Tensor([param_vals[1]]).cuda()))
        self.register_parameter(name='k_r_pitch', param=torch.nn.Parameter(torch.Tensor([param_vals[2]]).cuda()))
        # roll dynamics
        self.register_parameter(name='w_natural_Hz_roll', param=torch.nn.Parameter(torch.Tensor([param_vals[3]]).cuda()))
        self.register_parameter(name='k_f_roll', param=torch.nn.Parameter(torch.Tensor([param_vals[4]]).cuda()))
        self.register_parameter(name='k_r_roll', param=torch.nn.Parameter(torch.Tensor([param_vals[5]]).cuda()))

        


    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm
        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1
        #damping = self.minmax_scale_hm(0.01,0.99,constraint_weights(self.damping)) # this needs to be either in (0,1), 1 or (1,inf]

        w_natural_Hz_pitch = self.minmax_scale_hm(0.75,7,constraint_weights(self.w_natural_Hz_pitch))
        k_scale = 1
        k_f_pitch = self.minmax_scale_hm(-k_scale,0,constraint_weights(self.k_f_pitch))
        k_r_pitch = self.minmax_scale_hm(-k_scale,0,constraint_weights(self.k_r_pitch))

        w_natural_Hz_roll = self.minmax_scale_hm(0.75,7,constraint_weights(self.w_natural_Hz_roll))
        k_f_roll = self.minmax_scale_hm(-k_scale,0,constraint_weights(self.k_f_roll))
        k_r_roll = self.minmax_scale_hm(-k_scale,0,constraint_weights(self.k_r_roll))


        return [w_natural_Hz_pitch,k_f_pitch,k_r_pitch,w_natural_Hz_roll,k_f_roll,k_r_roll]

    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    

    def produce_past_action_coefficients(self,w_natural_Hz,length):
        # Generate the k coefficients for past actions
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        k_vec = torch.zeros((length,1)).cuda()
        k_dev_vec = torch.zeros((length,1)).cuda()
        for i in range(length):
            k_vec[i], k_dev_vec[i] = self.impulse_response(i*self.dt,w_natural_Hz) # 
        # the dt is really important to get the amplitude right
        k_vec = k_vec * self.dt
        k_dev_vec = k_dev_vec * self.dt
        return k_vec.double() ,  k_dev_vec.double()   


    def impulse_response(self,t,w_natural_Hz):
        #second order impulse response
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        w = w_natural_Hz * 2 *np.pi # convert to rad/s

        f = w**2 * t * torch.exp(-w*t)
        f_dev = w**2 * (torch.exp(-w*t)-w*t*torch.exp(-w*t)) 
        return f ,f_dev




    def forward(self, train_x):  # this is the model that will be fitted
        F_y_model_front = torch.unsqueeze(train_x[:,0],1)
        F_y_model_rear = torch.unsqueeze(train_x[:,1],1)
        past_acc_longitudinal = train_x[:,2:self.n_past_actions+2]
        past_acc_lateral = train_x[:,self.n_past_actions+2:]
 
        [w_natural_Hz_pitch,k_f_pitch,k_r_pitch,w_natural_Hz_roll,k_f_roll,k_r_roll] = self.transform_parameters_norm_2_real()


        #produce past action coefficients
        k_vec_pitch,k_dev_vec_pitch = self.produce_past_action_coefficients(w_natural_Hz_pitch,self.n_past_actions) # 
        k_vec_roll,k_dev_vec_roll = self.produce_past_action_coefficients(w_natural_Hz_roll,self.n_past_actions) 

        # convert to rad/s
        w_natural_pitch = w_natural_Hz_pitch * 2 *np.pi
        w_natural_roll = w_natural_Hz_roll * 2 *np.pi

        # pitch dynamics
        c_pitch = 2 * w_natural_pitch 
        k_pitch = w_natural_pitch**2
        F_z_tilde_pitch = past_acc_longitudinal @ k_vec_pitch + c_pitch/k_pitch * past_acc_longitudinal @ k_dev_vec_pitch # this is the non-scaled response (we don't know the magnitude of the input)

        # roll dynamics
        c_roll = 2 * w_natural_roll 
        k_roll = w_natural_roll**2
        F_z_tilde_roll = past_acc_lateral @ k_vec_roll + c_roll/k_roll * past_acc_lateral @ k_dev_vec_roll # this is the non-scaled response (we don't know the magnitude of the input)


        # correction term pitch
        alpha_z_front_pitch = F_z_tilde_pitch * k_f_pitch * (self.lr)/(self.lr+self.lf)   # lf and lr should be scaled by the other length (lr lf are switched)
        alpha_z_rear_pitch = F_z_tilde_pitch * -k_f_pitch * (self.lf)/(self.lr+self.lf) # k_r_pitch

        # correction term roll
        alpha_z_front_roll = F_z_tilde_roll * k_f_roll
        alpha_z_rear_roll = F_z_tilde_roll * k_f_roll #k_r_roll


        F_y_front = F_y_model_front * (1+alpha_z_front_pitch+alpha_z_front_roll) #+ alpha_z_front_pitch * F_y_model_front + alpha_z_front_roll #* F_y_model_front
        F_y_rear  = F_y_model_rear * (1+alpha_z_rear_pitch+alpha_z_front_roll)  #+ alpha_z_rear_roll  + alpha_z_rear_pitch * F_y_model_rear


        return F_y_front, F_y_rear, past_acc_longitudinal @ k_vec_pitch, past_acc_lateral @ k_vec_roll


class full_model_with_pitch_and_roll_dynamics(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals,dt,n_past_actions,lr,lf):
        super(full_model_with_pitch_and_roll_dynamics, self).__init__()

        # NOTE:
        # if the chosen dynamics are longer than the amount of samples you have, you can in the end subtract energy from the signal,
        # so if you see that the settling point of the new steering command is lower than what you expect, you can increase the number of past actions
        # or give the freedom to change also the steering curve

        self.dt = dt
        self.n_past_actions = n_past_actions
        self.lr = lr
        self.lf = lf

        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        # pitch_dynamics
        self.register_parameter(name='w_natural_Hz_pitch', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='k_f_pitch', param=torch.nn.Parameter(torch.Tensor([param_vals[1]]).cuda()))
        self.register_parameter(name='k_r_pitch', param=torch.nn.Parameter(torch.Tensor([param_vals[2]]).cuda()))
        # roll dynamics
        self.register_parameter(name='w_natural_Hz_roll', param=torch.nn.Parameter(torch.Tensor([param_vals[3]]).cuda()))
        self.register_parameter(name='k_f_roll', param=torch.nn.Parameter(torch.Tensor([param_vals[4]]).cuda()))
        self.register_parameter(name='k_r_roll', param=torch.nn.Parameter(torch.Tensor([param_vals[5]]).cuda()))


        # load model paremeters
        [theta_correction, lr, l_COM, Jz, lf, m,
        a_m, b_m, c_m, d_m,
        a_f, b_f, c_f, d_f,
        a_s, b_s, c_s, d_s, e_s,
        d_t, c_t, b_t,
        a_stfr, b_stfr,d_stfr,e_stfr,f_stfr,g_stfr,
        max_st_dot,fixed_delay_stdn,k_stdn,
        w_natural_Hz_pitch,k_f_pitch,k_r_pitch,
        w_natural_Hz_roll,k_f_roll,k_r_roll] = model_parameters()

        self.m = m
        self.l_COM = l_COM
        self.lr = lr
        self.lf = lf
        self.Jz = Jz

        # Tire model
        self.d_t = d_t
        self.c_t = c_t
        self.b_t = b_t

        # Motor curve
        self.a_m =  a_m
        self.b_m =  b_m
        self.c_m =  c_m

        #Friction curve
        self.a_f =  a_f
        self.b_f =  b_f
        self.c_f =  c_f
        self.d_f =  d_f

        # extra friction due to steering
        self.a_stfr = a_stfr
        self.b_stfr = b_stfr
        self.d_stfr = d_stfr
        self.e_stfr = e_stfr
        self.f_stfr = f_stfr
        self.g_stfr = g_stfr





    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm
        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1
        #damping = self.minmax_scale_hm(0.01,0.99,constraint_weights(self.damping)) # this needs to be either in (0,1), 1 or (1,inf]

        w_natural_Hz_pitch = self.minmax_scale_hm(0.75,7,constraint_weights(self.w_natural_Hz_pitch))
        k_scale = 0.2
        k_f_pitch = self.minmax_scale_hm(-k_scale,k_scale,constraint_weights(self.k_f_pitch))
        k_r_pitch = self.minmax_scale_hm(-k_scale,0,constraint_weights(self.k_r_pitch))

        w_natural_Hz_roll = self.minmax_scale_hm(0.75,7,constraint_weights(self.w_natural_Hz_roll))
        k_f_roll = self.minmax_scale_hm(-k_scale,0,constraint_weights(self.k_f_roll))
        k_r_roll = self.minmax_scale_hm(-k_scale,0,constraint_weights(self.k_r_roll))


        return [w_natural_Hz_pitch,k_f_pitch,k_r_pitch,w_natural_Hz_roll,k_f_roll,k_r_roll]

    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    

    def produce_past_action_coefficients(self,w_natural_Hz,length):
        # Generate the k coefficients for past actions
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        k_vec = torch.zeros((length,1)).cuda()
        k_dev_vec = torch.zeros((length,1)).cuda()
        for i in range(length):
            k_vec[i], k_dev_vec[i] = self.impulse_response(i*self.dt,w_natural_Hz) # 
        # the dt is really important to get the amplitude right
        k_vec = k_vec * self.dt
        k_dev_vec = k_dev_vec * self.dt
        return k_vec.double() ,  k_dev_vec.double()   


    def impulse_response(self,t,w_natural_Hz):
        #second order impulse response
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        w = w_natural_Hz * 2 *np.pi # convert to rad/s

        f = w**2 * t * torch.exp(-w*t)
        f_dev = w**2 * (torch.exp(-w*t)-w*t*torch.exp(-w*t)) 
        return f ,f_dev




    def forward(self, train_x):  # this is the model that will be fitted
        # training_x = [vx vy w, steering values]
        vx = torch.unsqueeze(train_x[:,0],1)
        vy = torch.unsqueeze(train_x[:,1],1) 
        w = torch.unsqueeze(train_x[:,2],1)
        throttle = torch.unsqueeze(train_x[:,3],1)
        steering_angle = torch.unsqueeze(train_x[:,4],1)

        # past accelerations
        past_acc_longitudinal = train_x[:,5:self.n_past_actions+5]
        past_acc_lateral = train_x[:,self.n_past_actions+5:]
 
        [w_natural_Hz_pitch,k_f_pitch,k_r_pitch,w_natural_Hz_roll,k_f_roll,k_r_roll] = self.transform_parameters_norm_2_real()


        #produce past action coefficients
        k_vec_pitch,k_dev_vec_pitch = self.produce_past_action_coefficients(w_natural_Hz_pitch,self.n_past_actions) # 
        k_vec_roll,k_dev_vec_roll = self.produce_past_action_coefficients(w_natural_Hz_roll,self.n_past_actions) 

        # convert to rad/s
        w_natural_pitch = w_natural_Hz_pitch * 2 *np.pi
        w_natural_roll = w_natural_Hz_roll * 2 *np.pi

        # pitch dynamics
        c_pitch = 2 * w_natural_pitch 
        k_pitch = w_natural_pitch**2
        F_z_tilde_pitch = past_acc_longitudinal @ k_vec_pitch + c_pitch/k_pitch * past_acc_longitudinal @ k_dev_vec_pitch # this is the non-scaled response (we don't know the magnitude of the input)

        # roll dynamics
        c_roll = 2 * w_natural_roll 
        k_roll = w_natural_roll**2
        F_z_tilde_roll = past_acc_lateral @ k_vec_roll + c_roll/k_roll * past_acc_lateral @ k_dev_vec_roll # this is the non-scaled response (we don't know the magnitude of the input)


        # correction term pitch
        alpha_z_front_pitch = F_z_tilde_pitch * k_f_pitch * (self.lr)/(self.lr+self.lf)   # lf and lr should be scaled by the other length (lr lf are switched)
        alpha_z_rear_pitch = F_z_tilde_pitch * -k_f_pitch * (self.lf)/(self.lr+self.lf) # k_r_pitch

        # correction term roll
        alpha_z_front_roll = F_z_tilde_roll * k_f_roll
        alpha_z_rear_roll = F_z_tilde_roll * k_f_roll #k_r_roll


        # evaluate longitudinal forces
        Fx = + self.motor_force(throttle,vx,self.a_m,self.b_m,self.c_m) \
             + self.rolling_friction(vx,self.a_f,self.b_f,self.c_f,self.d_f)\
             + self.F_friction_due_to_steering(steering_angle,vx,self.a_stfr,self.b_stfr,self.d_stfr,self.e_stfr,self.f_stfr,self.g_stfr) 
        
        Fx_front = Fx/2
        Fx_rear = Fx/2

        # evaluate lateral tire forces
        Vy_wheel_f,Vy_wheel_r = self.evalaute_wheel_lateral_velocities(vx,vy,w,steering_angle,self.lf,self.lr)

        Fy_wheel_f = self.lateral_tire_force(Vy_wheel_f,self.d_t,self.c_t,self.b_t)
        Fy_wheel_r = self.lateral_tire_force(Vy_wheel_r,self.d_t,self.c_t,self.b_t)

        # CORRECT TIRE FORCES WITH ROLL PITCH MODIFIERS
        # front tire forces
        Fx_front = Fx_front * (1+alpha_z_front_pitch) 
        F_y_front = Fy_wheel_f * (1+alpha_z_front_pitch) 
        # rear tire forces
        Fx_rear = Fx_rear * (1+alpha_z_rear_pitch)
        F_y_rear  = Fy_wheel_r * (1+alpha_z_rear_pitch) 

        acc_x,acc_y,acc_w = self.solve_rigid_body_dynamics(vx,vy,w,steering_angle,Fx_front,Fx_rear,F_y_front,F_y_rear,self.lf,self.lr,self.m,self.Jz)


        return acc_x,acc_y,acc_w, past_acc_longitudinal @ k_vec_pitch, past_acc_lateral @ k_vec_roll

































class fullmodel_with_steering_dynamics_model(torch.nn.Sequential):
    def __init__(self,param_vals,n_past_steering,dt):
        super(fullmodel_with_steering_dynamics_model, self).__init__()

        # NOTE:
        # if the chosen dynamics are longer than the amount of samples you have, you can in the end subtract energy from the signal,
        # so if you see that the settling point of the new steering command is lower than what you expect, you can increase the number of past actions
        # or give the freedom to change also the steering curve

        self.dt = dt
        self.n_past_steering = n_past_steering

        #define relu for later use
        self.relu = torch.nn.ReLU()

        # get model parameters
        [theta_correction, self.lr, self.l_COM, self.Jz, self.lf, self.m,
        self.a_m, self.b_m, self.c_m, self.d_m,
        self.a_f, self.b_f, self.c_f, self.d_f,
        a_s, b_s, c_s, d_s,e_s,
        d_t, c_t, b_t,
        self.a_stfr, self.b_stfr] = model_parameters()

        # # steering curve coefficients
        # self.a_s = a_s
        # self.b_s = b_s
        # self.c_s = c_s
        # self.d_s = d_s
        # self.e_s = e_s
        # # length of vehicle
        # self.lf = lf
        # self.lr = lr

        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        #steering dynamics parameters
        self.register_parameter(name='damping', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='w_natural', param=torch.nn.Parameter(torch.Tensor([param_vals[1]]).cuda()))
        self.register_parameter(name='fixed_delay', param=torch.nn.Parameter(torch.Tensor([param_vals[2]]).cuda()))

        # also tweeaking the steering curve
        self.register_parameter(name='a_s', param=torch.nn.Parameter(torch.Tensor(param_vals[3])))
        self.register_parameter(name='b_s', param=torch.nn.Parameter(torch.Tensor(param_vals[4])))
        self.register_parameter(name='c_s', param=torch.nn.Parameter(torch.Tensor(param_vals[5])))
        self.register_parameter(name='d_s', param=torch.nn.Parameter(torch.Tensor(param_vals[6])))
        self.register_parameter(name='e_s', param=torch.nn.Parameter(torch.Tensor(param_vals[7])))

        # tire curve model
               # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        self.register_parameter(name='d_t', param=torch.nn.Parameter(torch.Tensor([param_vals[8]]).cuda()))
        self.register_parameter(name='c_t', param=torch.nn.Parameter(torch.Tensor([param_vals[9]]).cuda()))
        self.register_parameter(name='b_t', param=torch.nn.Parameter(torch.Tensor([param_vals[10]]).cuda()))




        
    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm

        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1

        #damping = self.minmax_scale_hm(0.01,0.99,constraint_weights(self.damping)) # this needs to be either in (0,1), 1 or (1,inf]
        damping = self.minmax_scale_hm(0.6,0.99,constraint_weights(self.damping))
        w_natural = self.minmax_scale_hm(0.1,20,constraint_weights(self.w_natural))
        fixed_delay = self.minmax_scale_hm(0.0,0.3,constraint_weights(self.fixed_delay))

        # tweaking steering curve
        # a_s =  1.3210240602493286
        # b_s =  0.3621985912322998
        # c_s =  -0.0707419216632843
        # d_s =  0.4886220097541809
        # e_s =  1.0393908023834229

        # a_s = self.minmax_scale_hm(1.32,1.33,constraint_weights(self.a_s))
        # b_s = self.minmax_scale_hm(0.36,0.37,constraint_weights(self.b_s))
        # c_s = self.minmax_scale_hm(-0.08,-0.07,constraint_weights(self.c_s))
        # d_s = self.minmax_scale_hm(0.48,0.49,constraint_weights(self.d_s))
        # e_s = self.minmax_scale_hm(1.039,1.04,constraint_weights(self.e_s))

        #a_s =  1.3561502695083618
        # b_s =  0.3870258927345276
        # c_s =  -0.016262762248516083
        # d_s =  0.5085058212280273
        # e_s =  1.0010278224945068

        a_s = self.minmax_scale_hm(1.0,1.5,constraint_weights(self.a_s))
        b_s = self.minmax_scale_hm(0.2,0.6,constraint_weights(self.b_s))
        c_s = self.minmax_scale_hm(-0.1,+0.1,constraint_weights(self.c_s))
        d_s = self.minmax_scale_hm(0.20,0.70,constraint_weights(self.d_s))
        e_s = self.minmax_scale_hm(0.5,1.5,constraint_weights(self.e_s))
        # wheel model
        # a_s =  1.3561502695083618
        # b_s =  0.3870258927345276
        # c_s =  -0.016262762248516083
        # d_s =  0.5085058212280273
        # e_s =  1.0010278224945068

        # tire model
        # d_t =  -7.428709983825684
        # c_t =  0.7740796804428101
        # b_t =  4.992660999298096

        d_t = self.minmax_scale_hm(-7,-10,constraint_weights(self.d_t))
        c_t = self.minmax_scale_hm(0.5,1.0,constraint_weights(self.c_t))
        b_t = self.minmax_scale_hm(0.01,10,constraint_weights(self.b_t))
    

        return [damping,w_natural,fixed_delay,a_s,b_s,c_s,d_s,e_s,d_t,c_t,b_t]
        
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)
    
    def produce_past_action_coefficients(self,damping,w_natural,fixed_delay):
        # Generate the k coefficients for past actions
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        k_vec = torch.zeros((self.n_past_steering,1)).cuda()
        for i in range(self.n_past_steering):
            k_vec[i]=self.impulse_response(i*self.dt,damping,w_natural,fixed_delay)
        return k_vec * self.dt  # the dt is really important to get the amplitude right

    def impulse_response(self,t_tilde,damping,w_natural,fixed_delay):
        #second order impulse response
        #[d,c,b,damping,w_natural] = self.transform_parameters_norm_2_real()
        w = w_natural * 2 *np.pi # convert to rad/s
        z = damping

        # add fixed time delay
        t = self.relu(t_tilde-fixed_delay)
        #t = (0.5*torch.tanh(50*(t_tilde-fixed_delay))+0.5)*(t_tilde-fixed_delay)

        # different responses for different damping ratios
        if z >1:
            a = torch.sqrt(z**2-1)
            f = w/(2*a) * (torch.exp(-w*(z-a)*t) - torch.exp(-w*(z+a)*t))

        elif z == 1:
            f = w**2 * t * torch.exp(-w*t)

        elif z < 1:
            w_d = w * torch.sqrt(1-z**2)
            f = w/(torch.sqrt(1-z**2))*torch.exp(-z*w*t)*torch.sin(w_d*t)

        return f
    
    def motor_force(self,th,v):
        w = 0.5 * (torch.tanh(100*(th+self.c_m))+1)
        Fm =  (self.a_m - v * self.b_m) * w * (th+self.c_m)
        return Fm

    def friction(self,v):
        Ff = - ( self.a_f * torch.tanh(self.b_f  * v) + self.c_f * v + self.d_f * v**2 )
        return Ff
    
    def friction_due_to_steering(self,vx,steer_angle):
        return self.friction(vx) * self.a_stfr * torch.tanh(self.b_stfr * steer_angle**2)

    def F_y_wheel_model(self,vy_wheel,d_t,c_t,b_t):
        F_y_wheel = d_t * torch.sin(c_t * torch.arctan(b_t * vy_wheel )) 
        return F_y_wheel
    

    def forward(self, train_x):  # this is the model that will be fitted
        # training_x = [vx vy w, steering values]
        vx = torch.unsqueeze(train_x[:,0],1)
        vy = torch.unsqueeze(train_x[:,1],1) 
        w = torch.unsqueeze(train_x[:,2],1)
        throttle = torch.unsqueeze(train_x[:,3],1)

        
        [damping,w_natural,fixed_delay,a_s,b_s,c_s,d_s,e_s,d_t,c_t,b_t] = self.transform_parameters_norm_2_real()

        #produce past action coefficients
        k_vec = self.produce_past_action_coefficients(damping,w_natural,fixed_delay).double()
        steering_integrated = train_x[:,-(self.n_past_steering):] @ k_vec



        # here basically we solve the dymamics of the robot as we would do in the simulation
        #evaluate steering angle 
        w_s = 0.5 * (torch.tanh(30*(steering_integrated+c_s))+1)
        steering_angle1 = b_s * torch.tanh(a_s * (steering_integrated + c_s)) 
        steering_angle2 = d_s * torch.tanh(e_s * (steering_integrated + c_s)) 
        steering_angle = (w_s)*steering_angle1+(1-w_s)*steering_angle2

        # evaluate wheel velocities
        V_y_f_wheel = torch.cos(steering_angle)*(vy + self.lf*w) - torch.sin(steering_angle) * vx
        V_y_r_wheel = vy - self.lr*w

        # evalaute lateral tire force
        Fy_wheel_f = self.F_y_wheel_model(V_y_f_wheel,d_t,c_t,b_t)
        Fy_wheel_r = self.F_y_wheel_model(V_y_r_wheel,d_t,c_t,b_t)

        # evaluate motor force
        Fx = self.motor_force(throttle,vx) + self.friction(vx) + self.friction_due_to_steering(vx,steering_angle)
        
        #centrifugal force
        F_cent_x = + self.m * w * vy  # only y component of F is needed
        F_cent_y = - self.m * w * vx  # only y component of F is needed

        # evaluate body forces
        Fx_body = F_cent_x + Fx/2*(1+torch.cos(steering_angle)) + Fy_wheel_f * (-torch.sin(steering_angle))
        Fy_body = F_cent_y + Fx/2*(torch.sin(steering_angle)) + Fy_wheel_f * (torch.cos(steering_angle)) + Fy_wheel_r
        M       = Fx/2 * (+torch.sin(steering_angle)*self.lf) + Fy_wheel_f * (torch.cos(steering_angle)*self.lf)+\
                  Fy_wheel_r * (-self.lr) + F_cent_y * (-self.l_COM)
        # return accelerations in body frame plus other quantities useful for later plots
        return np.array([Fx_body/self.m,
                        Fy_body/self.m,
                        M/self.Jz,
                        steering_angle])  




class steering_friction_model(torch.nn.Sequential,model_functions):
    def __init__(self,param_vals,
                 m,m_front_wheel,m_rear_wheel,lr,lf,l_COM,Jz,
                 a_m,b_m,c_m,
                 a_f,b_f,c_f,d_f,
                 d_t_f, c_t_f, b_t_f,d_t_r, c_t_r, b_t_r):
        


        super(steering_friction_model, self).__init__()
        # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        self.register_parameter(name='a_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='d_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='e_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='f_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='g_stfr', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))

        self.register_parameter(name='a_s', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_s', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='c_s', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='d_s', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='e_s', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))

                # initialize parameters NOTE that the initial values should be [0,1], i.e. they should be the normalized value.
        self.register_parameter(name='d_t_f', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='c_t_f', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_t_f', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='d_t_r', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='c_t_r', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))
        self.register_parameter(name='b_t_r', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))

        # add pitch coefficient
        self.register_parameter(name='k_pitch', param=torch.nn.Parameter(torch.Tensor([param_vals[0]]).cuda()))



        self.m = m
        self.m_front_wheel = m_front_wheel
        self.m_rear_wheel = m_rear_wheel
        self.l_COM = l_COM
        self.lr = lr
        self.lf = lf
        self.Jz = Jz

        # Tire model 
        # front tire
        self.d_t_f_default = d_t_f
        self.c_t_f_default = c_t_f
        self.b_t_f_default = b_t_f

        # rear tire
        self.d_t_r_default = d_t_r
        self.c_t_r_default = c_t_r
        self.b_t_r_default = b_t_r

        # Motor curve
        self.a_m =  a_m
        self.b_m =  b_m
        self.c_m =  c_m

        #Friction curve
        self.a_f =  a_f
        self.b_f =  b_f
        self.c_f =  c_f
        self.d_f =  d_f


    def transform_parameters_norm_2_real(self):
        # Normalizing the fitting parameters is necessary to handle parameters that have different orders of magnitude.
        # This method converts normalized values to real values. I.e. maps from [0,1] --> [min_val, max_val]
        # so every parameter is effectively constrained to be within a certain range.
        # where min_val max_val are set here in this method as the first arguments of minmax_scale_hm

        constraint_weights = torch.nn.Hardtanh(0, 1) # this constraint will make sure that the parmeter is between 0 and 1

        #friction curve F= -  a * tanh(b  * v) - v * c
        a_stfr = self.minmax_scale_hm(0,10,constraint_weights(self.a_stfr))
        b_stfr = self.minmax_scale_hm(0,10,constraint_weights(self.b_stfr))
        d_stfr = self.minmax_scale_hm(0,20,constraint_weights(self.d_stfr))
        e_stfr = self.minmax_scale_hm(-6,0,constraint_weights(self.e_stfr))
        f_stfr = self.minmax_scale_hm(0,20,constraint_weights(self.f_stfr))
        g_stfr = self.minmax_scale_hm(0,20,constraint_weights(self.g_stfr))

        a_s = self.minmax_scale_hm(0.1,5,constraint_weights(self.a_s))
        b_s = self.minmax_scale_hm(0.2,0.6,constraint_weights(self.b_s))
        c_s = self.minmax_scale_hm(-0.1,0.1,constraint_weights(self.c_s))
        d_s = self.minmax_scale_hm(0.2,0.6,constraint_weights(self.d_s))
        e_s = self.minmax_scale_hm(0.1,5,constraint_weights(self.e_s))

        #friction curve F= -  a * tanh(b  * v) - v * c
        d_t_f = self.minmax_scale_hm(0,-10,constraint_weights(self.d_t_f))
        c_t_f = self.minmax_scale_hm(0,1,constraint_weights(self.c_t_f))
        b_t_f = self.minmax_scale_hm(0.01,1,constraint_weights(self.b_t_f))

        # rear tire
        d_t_r = self.minmax_scale_hm(0,-10,constraint_weights(self.d_t_r))
        c_t_r = self.minmax_scale_hm(0,1,constraint_weights(self.c_t_r))
        b_t_r = self.minmax_scale_hm(0.01,1,constraint_weights(self.b_t_r))

        # pitch coefficient
        k_pitch = self.minmax_scale_hm(0,10,constraint_weights(self.k_pitch))

        return [a_stfr,b_stfr,d_stfr,e_stfr,f_stfr,g_stfr,
                a_s,b_s,c_s,d_s,e_s,
                d_t_f,c_t_f,b_t_f,d_t_r,c_t_r,b_t_r,
                k_pitch]
        
    def minmax_scale_hm(self,min,max,normalized_value):
    # normalized value should be between 0 and 1
        return min + normalized_value * (max-min)

    
    def forward(self, train_x):  # this is the model that will be fitted
        
        #returns vx_dot,vy_dot,w_dot in the vehicle body frame
        # train_x = [ 'vx body', 'vy body', 'w', 'throttle' ,'steering angle'
        vx = torch.unsqueeze(train_x[:,0],1)
        vy = torch.unsqueeze(train_x[:,1],1) 
        w = torch.unsqueeze(train_x[:,2],1) 
        throttle = torch.unsqueeze(train_x[:,3],1) 
        steer_angle = torch.unsqueeze(train_x[:,4],1) 

        # Fx_wheels = torch.unsqueeze(train_x[:,5],1)
        # Fy_f = torch.unsqueeze(train_x[:,6],1)
        # Fy_r = torch.unsqueeze(train_x[:,7],1)
        # acc_x_input = torch.unsqueeze(train_x[:,8],1)



        [a_stfr,b_stfr,d_stfr,e_stfr,f_stfr,g_stfr,
                a_s,b_s,c_s,d_s,e_s,
                d_t_f,c_t_f,b_t_f,d_t_r,c_t_r,b_t_r,
                k_pitch] = self.transform_parameters_norm_2_real()

        # adjust real steering angle to account for reduction in steering angle at high speeds
        #steer_angle = steer_angle_original * (1 - k * vx * w)

        #steer_angle = self.steering_2_steering_angle(steer_command,a_s,b_s,c_s,d_s,e_s)

        F_friction_due_to_steering_val = self.F_friction_due_to_steering(steer_angle,vx,a_stfr,b_stfr,d_stfr,e_stfr,f_stfr,g_stfr)

        # # evaluate longitudinal forces
        Fx_wheels = + self.motor_force(throttle,vx,self.a_m,self.b_m,self.c_m)\
                    + self.rolling_friction(vx,self.a_f,self.b_f,self.c_f,self.d_f)\
                    + F_friction_due_to_steering_val 

        #Dm_f = - k_pitch * acc_x
        #Dm_r = + k_pitch * acc_x
        
        c_front = (self.m_front_wheel)/self.m # +Dm_f
        c_rear = (self.m_rear_wheel)/self.m # +Dm_r

        # redistribute Fx to front and rear wheels according to normal load
        Fx_front = Fx_wheels * c_front
        Fx_rear = Fx_wheels * c_rear

        # evaluate lateral tire forces
        #Vy_wheel_f, Vy_wheel_r = self.evalaute_wheel_lateral_velocities(vx,vy,w,steer_angle,self.lf,self.lr)

        #evaluate slip angles
        alpha_f,alpha_r = self.evaluate_slip_angles(vx,vy,w,self.lf,self.lr,steer_angle)


        # Fy_wheel_f = self.lateral_tire_force(Vy_wheel_f,self.d_t_f,self.c_t_f,self.b_t_f,self.m_front_wheel)
        # Fy_wheel_r = self.lateral_tire_force(Vy_wheel_r,self.d_t_r,self.c_t_r,self.b_t_r,self.m_rear_wheel)

        # front and rear normal loads
        mz_f = self.m_front_wheel # + Dm_f
        mz_r = self.m_rear_wheel #+ Dm_r

        Fy_wheel_f = self.lateral_tire_force(alpha_f,self.d_t_f_default,self.c_t_f_default,self.b_t_f_default,mz_f)
        Fy_wheel_r = self.lateral_tire_force(alpha_r,self.d_t_r_default,self.c_t_r_default,self.b_t_r_default,mz_r)

        acc_x,acc_y,acc_w = self.solve_rigid_body_dynamics(vx,vy,w,steer_angle,Fx_front,Fx_rear,Fy_wheel_f,Fy_wheel_r,self.lf,self.lr,self.m,self.Jz)

        return acc_x,acc_y,acc_w












def plot_motor_friction_curves(df,acceleration_curve_model_obj,fitting_friction):

    #plot motor characteristic curve
    tau_vec = torch.unsqueeze(torch.linspace(-1,1,100),1).cuda()
    v_vec = torch.unsqueeze(torch.linspace(0,df['vel encoder smoothed'].max(),100),1).cuda()
    data_vec = torch.cat((tau_vec, v_vec), 1)

    
    #plot friction curve
    friction_vec = acceleration_curve_model_obj.friction_curve(v_vec).detach().cpu().numpy()

    fig1, ((ax1)) = plt.subplots(1, 1, figsize=(10, 6), constrained_layout=True)
    ax1.plot(v_vec.cpu().numpy(),friction_vec,label = 'Friction curve',zorder=20,color='orangered',linewidth=5)
    ax1.set_xlabel('velocity [m\s]')
    ax1.set_ylabel('[N]')
    ax1.set_title('Friction curve')
    #ax1.grid()

    if fitting_friction:
        return ax1
    
    else:
        # also plot motor curve
        Fx_vec = acceleration_curve_model_obj.motor_curve(data_vec).detach().cpu().numpy()

        fig1, ((ax2)) = plt.subplots(1, 1, figsize=(10, 6), constrained_layout=True)
        ax2.plot(tau_vec.cpu().numpy(),Fx_vec,label = 'Th curve')
        ax2.set_title('Motor curve curve')
        ax2.set_xlabel('Throttle')
        ax2.set_ylabel('[N]')
        ax2.grid()

        return (ax1,ax2)
    






def produce_long_term_predictions(input_data, model,prediction_window,jumps,forward_propagate_indexes):
    # plotting long term predictions on data
    # each prediction window starts from a data point and then the quantities are propagated according to the provided model,
    # so they are not tied to the Vx Vy W data in any way. Though the throttle and steering inputs are taken from the data of course.

    # --- plot fitting results ---
    # input_data = ['vicon time', 'vx body', 'vy body', 'w', 'throttle' ,'steering','vicon x','vicon y','vicon yaw']

    #prepare tuple containing the long term predictions
    long_term_preds = ()
    


    # iterate through each prediction window
    print('------------------------------')
    print('producing long term predictions')
    from tqdm import tqdm
    tqdm_obj = tqdm(range(0,input_data.shape[0],jumps), desc="long term preds", unit="pred")

    for i in tqdm_obj:
        

        #reset couner
        k = 0
        elpsed_time_long_term_pred = 0

        # set up initial positions
        long_term_pred = np.expand_dims(input_data[i, :],0)


        # iterate through time indexes of each prediction window
        while elpsed_time_long_term_pred < prediction_window and k + i + 1 < len(input_data):
            #store time values
            #long_term_pred[k+1,0] = input_data[k+i, 0] 
            dt = input_data[i + k + 1, 0] - input_data[i + k, 0]
            elpsed_time_long_term_pred = elpsed_time_long_term_pred + dt

            #produce propagated state
            state_action_k = long_term_pred[k,[1,2,3,4,5]]
            
            # run it through the model
            accelrations = model.forward([*state_action_k]) # absolute accelerations in the current vehicle frame of reference
            
            # evaluate new state
            new_state_new_frame = long_term_pred[k,[1,2,3]] + accelrations * dt



            # chose quantities to forward propagate
            if 1 in forward_propagate_indexes:
                new_vx = new_state_new_frame[0]
            else:
                new_vx = input_data[i+k+1, 1]

            if 2 in forward_propagate_indexes:
                new_vy = new_state_new_frame[1]
            else:
                new_vy = input_data[i+k+1, 2]

            if 3 in forward_propagate_indexes:
                new_w = new_state_new_frame[2]
            else:
                new_w = input_data[i+k+1, 3] 

            new_state_new_frame = np.array([new_vx,new_vy,new_w])

            # forward propagate x y yaw state
            rot_angle = long_term_pred[k,8]
            R = np.array([
                [np.cos(rot_angle), -np.sin(rot_angle), 0],
                [np.sin(rot_angle), np.cos(rot_angle), 0],
                [0, 0, 1]
            ])

            # absolute velocities
            abs_vxvyw = R @ np.array([long_term_pred[k,1],long_term_pred[k,2],long_term_pred[k,3]])


            # propagate x y yaw according to the previous state
            new_xyyaw = np.array([long_term_pred[k,6],long_term_pred[k,7],long_term_pred[k,8]]) + abs_vxvyw * dt

            # put everything together
            new_row = np.array([input_data[i + k + 1, 0],*new_state_new_frame,input_data[k+i,4],input_data[k+i,5],*new_xyyaw])
            long_term_pred = np.vstack([long_term_pred, new_row])

            # update k
            k = k + 1

        long_term_preds += (long_term_pred,)  

    return long_term_preds









class dyn_model_culomb_tires(model_functions):
    def __init__(self,m,m_front_wheel,m_rear_wheel,lr,lf,l_COM,Jz,
                 a_m,b_m,c_m,
                 a_f,b_f,c_f,d_f,
                 d_t_f, c_t_f, b_t_f,d_t_r, c_t_r, b_t_r,
                 a_stfr, b_stfr,d_stfr,e_stfr,f_stfr,g_stfr):


        self.m = m
        self.m_front_wheel = m_front_wheel
        self.m_rear_wheel = m_rear_wheel
        self.l_COM = l_COM
        self.lr = lr
        self.lf = lf
        self.Jz = Jz

        # Tire model 
        # front tire
        self.d_t_f = d_t_f
        self.c_t_f = c_t_f
        self.b_t_f = b_t_f

        # rear tire
        self.d_t_r = d_t_r
        self.c_t_r = c_t_r
        self.b_t_r = b_t_r

        # Motor curve
        self.a_m =  a_m
        self.b_m =  b_m
        self.c_m =  c_m

        #Friction curve
        self.a_f =  a_f
        self.b_f =  b_f
        self.c_f =  c_f
        self.d_f =  d_f

        # extra friction due to steering
        self.a_stfr = a_stfr
        self.b_stfr = b_stfr
        self.d_stfr = d_stfr
        self.e_stfr = e_stfr
        self.f_stfr = f_stfr
        self.g_stfr = g_stfr


    def forward(self, state_action):
        #returns vx_dot,vy_dot,w_dot in the vehicle body frame
        #state_action = [vx,vy,w,throttle,steer,pitch,pitch_dot,roll,roll_dot]
        vx = state_action[0]
        vy = state_action[1]
        w = state_action[2]
        throttle = state_action[3]
        steer_angle = state_action[4]

        if len(state_action) > 5:
            Fx_wheels_input = state_action[5]
            Fy_f_input = state_action[6]
            Fy_r_input = state_action[7]
            alpha_r_input = state_action[8]
            alpha_f_input = state_action[9]


        if self.a_stfr:
            Fx_wheels = + self.motor_force(throttle,vx,self.a_m,self.b_m,self.c_m)\
                        + self.rolling_friction(vx,self.a_f,self.b_f,self.c_f,self.d_f)\
                        + self.F_friction_due_to_steering(vx,steer_angle,self.a_stfr,self.b_stfr,self.d_stfr,self.e_stfr,self.f_stfr,self.g_stfr)
        else:
            Fx_wheels = + self.motor_force(throttle,vx,self.a_m,self.b_m,self.c_m)\
                        + self.rolling_friction(vx,self.a_f,self.b_f,self.c_f,self.d_f)

        #Fx_wheels = Fx_wheels_input

        c_front = self.m_front_wheel/self.m
        c_rear = self.m_rear_wheel/self.m

        # redistribute Fx to front and rear wheels according to normal load
        Fx_front = Fx_wheels * c_front
        Fx_rear = Fx_wheels * c_rear

        # evaluate lateral tire forces
        #Vy_wheel_f, Vy_wheel_r = self.evalaute_wheel_lateral_velocities(vx,vy,w,steer_angle,self.lf,self.lr)

        #evaluate slip angles
        alpha_f,alpha_r = self.evaluate_slip_angles(vx,vy,w,self.lf,self.lr,steer_angle)

        # shut down forces if vehicle is standing still
        lat_F_activation = self.lateral_forces_activation_term(vx)

        Fy_wheel_f = self.lateral_tire_force(alpha_f,self.d_t_f,self.c_t_f,self.b_t_f,self.m_front_wheel) * lat_F_activation
        Fy_wheel_r = self.lateral_tire_force(alpha_r,self.d_t_r,self.c_t_r,self.b_t_r,self.m_rear_wheel) * lat_F_activation

        

        acc_x,acc_y,acc_w = self.solve_rigid_body_dynamics(vx,vy,w,steer_angle,
                                                           Fx_front,Fx_rear,
                                                           Fy_wheel_f,Fy_wheel_r,
                                                           self.lf,self.lr,self.m,self.Jz)

        return np.array([acc_x,acc_y,acc_w])
    
















class full_dynamic_model():
    def __init__(self, lr, l_COM, Jz, lf, m,
            a_m, b_m, c_m, d_m,
            a_f, b_f, c_f, d_f,
            a_s, b_s, c_s, d_s, e_s,
            d_t, c_t, b_t,
            a_stfr, b_stfr,d_stfr,e_stfr,f_stfr,g_stfr,
            max_st_dot,fixed_delay_stdn,k_stdn,
            w_natural_Hz_pitch,k_f_pitch,k_r_pitch,
            w_natural_Hz_roll,k_f_roll,k_r_roll
            ):


        self.m = m
        self.l_COM = l_COM
        self.lr = lr
        self.lf = lf
        self.Jz = Jz

        # Tire model
        self.d_t = d_t
        self.c_t = c_t
        self.b_t = b_t

        # Motor curve
        self.a_m =  a_m
        self.b_m =  b_m
        self.c_m =  c_m
        self.d_m =  d_m    

        #Friction curve
        self.a_f =  a_f
        self.b_f =  b_f
        self.c_f =  c_f
        self.d_f =  d_f

        # steering curve
        self.a_s = a_s
        self.b_s = b_s
        self.c_s = c_s
        self.d_s = d_s
        self.e_s = e_s

        # extra friction due to steering
        self.a_stfr = a_stfr
        self.b_stfr = b_stfr
        self.d_stfr = d_stfr
        self.e_stfr = e_stfr
        self.f_stfr = f_stfr
        self.g_stfr = g_stfr

        # steering dymamics parameters
        self.max_st_dot = max_st_dot
        self.fixed_delay_stdn = fixed_delay_stdn
        self.k_stdn = k_stdn

        #pitch dynamics parameters:
        self.w_natural_Hz_pitch = w_natural_Hz_pitch
        self.k_f_pitch = k_f_pitch
        self.k_r_pitch = k_r_pitch

        #roll dynamics parameters:
        self.w_natural_Hz_roll = w_natural_Hz_roll
        self.k_f_roll = k_f_roll
        self.k_r_roll = k_r_roll





    def motor_force(self,th,v):
        w = 0.5 * (np.tanh(100*(th+self.c_m))+1)
        Fm =  (self.a_m - v * self.b_m) * w * (th+self.c_m)
        return Fm

    def friction(self,v):
        Ff = - ( self.a_f * np.tanh(self.b_f  * v) + self.c_f * v + self.d_f * v**2 )
        return Ff
    
    def lateral_tire_forces(self,vy_wheel):
        Fy_wheel = self.d_t * np.sin(self.c_t * np.arctan(self.b_t * vy_wheel)) 
        return Fy_wheel
    
    def friction_due_to_steering(self,vx,steer_angle):
        w_friction_term = 0.5 * (np.tanh(30*(steer_angle))+1)
        friction_term_1 =  self.a_stfr * np.tanh(self.b_stfr * steer_angle**2) #b * (0.5 + 0.5 * torch.tanh(a * steer_angle)) # positve steering angle
        friction_term_2 =  self.e_stfr * np.tanh(self.d_stfr * steer_angle**2) #d * (0.5 + 0.5 * torch.tanh(e * steer_angle))
        friction_term = (w_friction_term)*friction_term_1+(1-w_friction_term)*friction_term_2 

        vx_term = (1 + self.f_stfr * np.exp(-self.g_stfr * vx**2)) * vx

        return  - friction_term * vx_term

    def critically_damped_2nd_order_dynamics(self,x_dot,x,forcing_term,w_Hz):
        z = 1 # critically damped system
        w_natural = w_Hz * 2 * np.pi # convert to rad/s

        x_dot_dot = w_natural ** 2 * (forcing_term - x) - 2* w_natural * z * x_dot
        return x_dot_dot
    
    def correct_F_y_roll_pitch(self,Fy_wheel_f,Fy_wheel_r,pitch,pitch_dot,roll,roll_dot):
        # apply correction terms due to roll and pitch dynamics
        # convert to rad/s
        w_natural_pitch = self.w_natural_Hz_pitch * 2 *np.pi

        # pitch dynamics
        c_pitch = 2 * w_natural_pitch 
        k_pitch = w_natural_pitch**2
        F_z_tilde_pitch = pitch + c_pitch/k_pitch * pitch_dot # this is the non-scaled response (we don't know the magnitude of the input)

        # correction term pitch
        alpha_z_front_pitch = F_z_tilde_pitch * self.k_f_pitch
        alpha_z_rear_pitch = F_z_tilde_pitch * self.k_r_pitch

        # roll dynamics
        w_natural_roll = self.w_natural_Hz_roll * 2 *np.pi
        c_roll = 2 * w_natural_roll
        k_roll = w_natural_roll**2

        F_z_tilde_roll = roll + c_roll/k_roll * roll_dot # this is the non-scaled response (we don't know the magnitude of the input)

        # correction term roll
        alpha_z_front_roll = F_z_tilde_roll * self.k_f_roll
        alpha_z_rear_roll = F_z_tilde_roll * self.k_r_roll

        Fy_wheel_f_corrected = Fy_wheel_f + alpha_z_front_pitch * Fy_wheel_f + alpha_z_front_roll 
        Fy_wheel_r_corrected  = Fy_wheel_r + alpha_z_rear_roll   + alpha_z_rear_pitch * Fy_wheel_r

        return Fy_wheel_f_corrected,Fy_wheel_r_corrected
    
    def forward(self, state_action):
        #returns vx_dot,vy_dot,w_dot in the vehicle body frame
        #state_action = [vx,vy,w,throttle_comand,steer_command,throttle,steering,pitch,pitch_dot,roll,roll_dot]

        #states
        vx = state_action[0]
        vy = state_action[1]
        w = state_action[2]
        # extra states need for subsystem dynamics
        throttle = state_action[3]
        steering = state_action[4]
        pitch_dot = state_action[5]
        pitch = state_action[6]
        roll_dot = state_action[7]
        roll = state_action[8]
        # inputs
        throttle_command = state_action[9]
        steering_command = state_action[10]


        # forwards integrate steering and throttle commands
        throttle_time_constant = 0.1 * self.d_m / (1 + self.d_m) # converting from discrete time to continuous time
        throttle_dot = (throttle_command - throttle) / throttle_time_constant

        # integrate steering
        st_dot = (steering_command - steering) / 0.01 * self.k_stdn
        # Apply max_st_dot limits
        st_dot = np.min([st_dot, self.max_st_dot])
        st_dot = np.max([st_dot, -self.max_st_dot])
        

        # evaluate steering angle
        w_s = 0.5 * (np.tanh(30*(steering))+1)
        steering_angle1 = self.b_s * np.tanh(self.a_s * (steering + self.c_s))
        steering_angle2 = self.d_s * np.tanh(self.e_s * (steering + self.c_s))
        steer_angle = (w_s)*steering_angle1+(1-w_s)*steering_angle2

        # Evaluate core dynamic model of the vehicle
        Fx_wheels = self.motor_force(throttle,vx) + self.friction(vx) + self.friction_due_to_steering(vx,steer_angle)
        Fx_front = Fx_wheels/2 
        Fx_rear = Fx_wheels/2 


        # evaluate lateral tire forces
        Vy_wheel_f = np.cos(steer_angle)*(vy + self.lf*w) - np.sin(steer_angle) * vx
        Vy_wheel_r = vy - self.lr*w

        Fy_wheel_f_base = self.lateral_tire_forces(Vy_wheel_f)
        Fy_wheel_r_base = self.lateral_tire_forces(Vy_wheel_r)

        # apply correction terms due to roll and pitch dynamics
        # Fy_wheel_f = Fy_wheel_f_base
        # Fy_wheel_r = Fy_wheel_r_base
        Fy_wheel_f,Fy_wheel_r = self.correct_F_y_roll_pitch(Fy_wheel_f_base,Fy_wheel_r_base,pitch,pitch_dot,roll,roll_dot)


        #centrifugal force
        F_cent_x = + self.m * w * vy  # only y component of F is needed
        F_cent_y = - self.m * w * vx  # only y component of F is needed


        # # --- TESTING TIRE FORCE SATURATION ---
        F_max = 200 # N

        F_f_wheel_abs = (Fx_front**2 + Fy_wheel_f**2)**0.5
        F_r_wheel_abs = (Fx_front**2 + Fy_wheel_r**2)**0.5

        f_max_rateo_front = F_f_wheel_abs / F_max
        f_max_rateo_rear  = F_r_wheel_abs / F_max
   

        # clip force rateo between at 1
        f_max_rateo_front_rescaled = np.min([f_max_rateo_front,1])

        f_max_rateo_rear_rescaled = np.min([f_max_rateo_rear,1])

        # # rescale forces
        Fx_front_rescaled = Fx_front * f_max_rateo_front / f_max_rateo_front_rescaled
        Fx_rear_rescaled = Fx_rear *   f_max_rateo_rear / f_max_rateo_rear_rescaled

        Fy_front_rescaled = Fy_wheel_f * f_max_rateo_front / f_max_rateo_front_rescaled
        Fy_rear_rescaled =  Fy_wheel_r * f_max_rateo_rear / f_max_rateo_rear_rescaled



        # # solve rigidbody dynamics
        # b = np.array(  [Fx_wheels/2,
        #                 Fy_wheel_f,
        #                 Fy_wheel_r,
        #                 F_cent_y])
        
        # A = np.array([  [1+np.cos(steer_angle),-np.sin(steer_angle),0,0],
        #                 [+np.sin(steer_angle),+np.cos(steer_angle),1,0],
        #                 [+np.sin(steer_angle)*self.lf  ,np.cos(steer_angle)*self.lf  ,-self.lr,-self.l_COM]])
        
        # solve rigidbody dynamics
        b = np.array(  [Fx_front_rescaled,
                        Fx_rear_rescaled,
                        Fy_front_rescaled,
                        Fy_rear_rescaled,
                        F_cent_y])
        
        A = np.array([  [np.cos(steer_angle),1,-np.sin(steer_angle),0,0],
                        [+np.sin(steer_angle),0,+np.cos(steer_angle),1,0],
                        [+np.sin(steer_angle)*self.lf, 0  ,np.cos(steer_angle)*self.lf  ,-self.lr,0]])  # -self.l_COM

        body_forces = A @ b

        Fx = body_forces[0]
        Fy = body_forces[1]
        M  = body_forces[2]





        # evaluate accelerations in body frame
        acc_x = (Fx+F_cent_x)/self.m
        acc_y = (Fy+F_cent_y)/self.m
        acc_yaw = M/self.Jz

        # evaluate pitch dynamics (excess with respect to the static case)
        pitch_dot_dot = self.critically_damped_2nd_order_dynamics(pitch_dot,pitch,acc_x,self.w_natural_Hz_pitch)

        #evaluate roll dynamics
        roll_dot_dot = self.critically_damped_2nd_order_dynamics(roll_dot,roll,acc_y,self.w_natural_Hz_roll)

        return np.array([acc_x,
                         acc_y,
                         acc_yaw,
                         throttle_dot,
                         st_dot,
                         pitch_dot_dot,
                         pitch_dot,
                         roll_dot_dot,
                         roll_dot])



def produce_long_term_predictions_full_model(input_data, model,prediction_window,jumps,forward_propagate_indexes):
    # plotting long term predictions on data
    # each prediction window starts from a data point and then the quantities are propagated according to the provided model,
    # so they are not tied to the Vx Vy W data in any way. Though the throttle and steering inputs are taken from the data of course.

    # --- plot fitting results ---
    # input_data = ['vicon time',   0
                #   'vx body',      1
                #   'vy body',      2
                #   'w',        3
                #   'throttle integrated' ,  4
                #   'steering integrated',   5
                #   'pitch dot',    6
                #   'pitch',        7
                #   'roll dot',     8
                #   'roll',         9
                #   'throttle',     10
                #   'steering',     11
                #   'vicon x',      12
                #   'vicon y',      13
                #   'vicon yaw']    14

    #prepare tuple containing the long term predictions
    long_term_preds = ()
    


    # iterate through each prediction window
    print('------------------------------')
    print('producing long term predictions')
    from tqdm import tqdm
    tqdm_obj = tqdm(range(0,input_data.shape[0],jumps), desc="long term preds", unit="pred")

    for i in tqdm_obj:
        

        #reset couner
        k = 0
        elpsed_time_long_term_pred = 0

        # set up initial positions
        long_term_pred = np.expand_dims(input_data[i, :],0)


        # iterate through time indexes of each prediction window
        while elpsed_time_long_term_pred < prediction_window and k + i + 1 < len(input_data):
            #store time values
            #long_term_pred[k+1,0] = input_data[k+i, 0] 
            dt = input_data[i + k + 1, 0] - input_data[i + k, 0]
            elpsed_time_long_term_pred = elpsed_time_long_term_pred + dt

            #produce propagated state
            state_action_k = long_term_pred[k,1:12]
            
            # run it through the model
            accelrations = model.forward(state_action_k) # absolute accelerations in the current vehicle frame of reference
            
            # evaluate new state
            new_state_new_frame = np.zeros(9)

            for prop_index in range(1,10):
                # chose quantities to forward propagate
                if prop_index in forward_propagate_indexes:
                    new_state_new_frame[prop_index-1] = long_term_pred[k,prop_index] + accelrations[prop_index-1] * dt 
                else:
                    new_state_new_frame[prop_index-1] = input_data[i+k+1, prop_index]


            # forward propagate x y yaw state
            rot_angle = long_term_pred[k,14]
            R = np.array([
                [np.cos(rot_angle), -np.sin(rot_angle), 0],
                [np.sin(rot_angle), np.cos(rot_angle), 0],
                [0, 0, 1]
            ])

            # absolute velocities from previous time instant
            abs_vxvyw = R @ np.array([long_term_pred[k,1],long_term_pred[k,2],long_term_pred[k,3]])


            # propagate x y yaw according to the previous state
            new_xyyaw = np.array([long_term_pred[k,12],long_term_pred[k,13],long_term_pred[k,14]]) + abs_vxvyw * dt

            # put everything together
            new_row = np.array([input_data[i + k + 1, 0],*new_state_new_frame,input_data[i+k+1,10],input_data[i+k+1,11],*new_xyyaw])
            long_term_pred = np.vstack([long_term_pred, new_row])

            # update k
            k = k + 1

        long_term_preds += (long_term_pred,)  

    return long_term_preds











import torch
import gpytorch
import tqdm
import random
from gpytorch.models import ApproximateGP
from gpytorch.variational import CholeskyVariationalDistribution
from gpytorch.variational import VariationalStrategy



# SVGP 
class SVGPModel(ApproximateGP):
    def __init__(self, inducing_points):
        variational_distribution = CholeskyVariationalDistribution(inducing_points.size(0))
        variational_strategy = VariationalStrategy(self, inducing_points, variational_distribution, learn_inducing_locations=True)
        super(SVGPModel, self).__init__(variational_strategy)
        self.mean_module = gpytorch.means.ZeroMean()
        self.covar_module = gpytorch.kernels.ScaleKernel(gpytorch.kernels.RBFKernel(ard_num_dims=inducing_points.size(dim=1)))

    def forward(self, x):
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)




def train_SVGP_model(learning_rate,num_epochs, train_x, train_y_vx, train_y_vy, train_y_w, n_inducing_points):
    
    # start fitting
    # make contiguous (not sure why)
    train_x = train_x.contiguous()
    train_y_vx = train_y_vx.contiguous()
    train_y_vy = train_y_vy.contiguous()
    train_y_w = train_y_w.contiguous()

    # define batches for training (each bach will be used to perform a gradient descent step in each iteration. So toal parameters updates are Epochs*n_batches)
    from torch.utils.data import TensorDataset, DataLoader
    train_dataset_vx = TensorDataset(train_x, train_y_vx)
    train_dataset_vy = TensorDataset(train_x, train_y_vy)
    train_dataset_w = TensorDataset(train_x, train_y_w)

    # define data loaders
    train_loader_vx = DataLoader(train_dataset_vx, batch_size=250, shuffle=True)
    train_loader_vy = DataLoader(train_dataset_vy, batch_size=250, shuffle=True)
    train_loader_w = DataLoader(train_dataset_w, batch_size=250, shuffle=True)

    #choosing initial guess inducing points as a random subset of the training data
    random.seed(10) # set the seed so to have same points for every run
    # random selection of inducing points
    random_indexes = random.choices(range(train_x.shape[0]), k=n_inducing_points)
    inducing_points = train_x[random_indexes, :]

    inducing_points = inducing_points.to(torch.float32)

    #initialize models
    model_vx = SVGPModel(inducing_points=inducing_points)
    model_vy = SVGPModel(inducing_points=inducing_points)
    model_w = SVGPModel(inducing_points=inducing_points)


    # assign first guess lengthscales
    #                                                            vx, vy ,w, throttle,steer
    model_vx.covar_module.base_kernel.lengthscale = torch.tensor([0.1,1,10,  0.1,    1])
    model_vy.covar_module.base_kernel.lengthscale = torch.tensor([1,1,10,10,1])
    model_w.covar_module.base_kernel.lengthscale =  torch.tensor([2,2,2,2,2])


    # Assign training data to models just to have it all together for later plotting
    model_vx.train_x = train_x 
    model_vx.train_y_vx = train_y_vx

    model_vy.train_x = train_x 
    model_vy.train_y_vy = train_y_vy

    model_w.train_x = train_x 
    model_w.train_y_w = train_y_w


    #define likelyhood objects
    likelihood_vx = gpytorch.likelihoods.GaussianLikelihood()
    likelihood_vy = gpytorch.likelihoods.GaussianLikelihood()
    likelihood_w = gpytorch.likelihoods.GaussianLikelihood()
 


    #move to GPU for faster fitting
    if torch.cuda.is_available():
        model_vx = model_vx.cuda()
        model_vy = model_vy.cuda()
        model_w = model_w.cuda()
        likelihood_vx = likelihood_vx.cuda()
        likelihood_vy = likelihood_vy.cuda()
        likelihood_w = likelihood_w.cuda()

    #set to training mode
    model_vx.train()
    model_vy.train()
    model_w.train()
    likelihood_vx.train()
    likelihood_vy.train()
    likelihood_w.train()

    #set up optimizer and its options
    optimizer_vx = torch.optim.AdamW([{'params': model_vx.parameters()}, {'params': likelihood_vx.parameters()},], lr=learning_rate)
    optimizer_vy = torch.optim.AdamW([{'params': model_vy.parameters()}, {'params': likelihood_vy.parameters()},], lr=learning_rate)
    optimizer_w = torch.optim.AdamW([{'params': model_w.parameters()}, {'params': likelihood_w.parameters()},], lr=learning_rate)


    # Set up loss object. We're using the VariationalELBO
    mll_vx = gpytorch.mlls.VariationalELBO(likelihood_vx, model_vx, num_data=train_y_vx.size(0))#, beta=1)
    mll_vy = gpytorch.mlls.VariationalELBO(likelihood_vy, model_vy, num_data=train_y_vy.size(0))#, beta=1)
    mll_w = gpytorch.mlls.VariationalELBO(likelihood_w, model_w, num_data=train_y_w.size(0))#, beta=1)

    # start training (tqdm is just to show the loading bar)
    epochs_iter = tqdm.tqdm(range(num_epochs), desc="Epoch")



    loss_2_print_vx_vec = []
    loss_2_print_vy_vec = []
    loss_2_print_w_vec = []

    for i in epochs_iter:
        # Within each iteration, we will go over each minibatch of data
        minibatch_iter_vx = tqdm.tqdm(train_loader_vx, desc="Minibatch vx", leave=False, disable=True)
        minibatch_iter_vy = tqdm.tqdm(train_loader_vy, desc="Minibatch vy", leave=False, disable=True)
        minibatch_iter_w  = tqdm.tqdm(train_loader_w,  desc="Minibatch w",  leave=False, disable=True)

        for x_batch_vx, y_batch_vx in minibatch_iter_vx:
            optimizer_vx.zero_grad()
            output_vx = model_vx(x_batch_vx)
            loss_vx = -mll_vx(output_vx, y_batch_vx[:,0])
            minibatch_iter_vx.set_postfix(loss=loss_vx.item())
            loss_vx.backward()
            optimizer_vx.step()

        loss_2_print_vx_vec = [*loss_2_print_vx_vec, loss_vx.item()]

        for x_batch_vy, y_batch_vy in minibatch_iter_vy:
            optimizer_vy.zero_grad()
            output_vy = model_vy(x_batch_vy)
            loss_vy = -mll_vy(output_vy, y_batch_vy[:,0])
            minibatch_iter_vy.set_postfix(loss=loss_vy.item())
            loss_vy.backward()
            optimizer_vy.step()

        loss_2_print_vy_vec = [*loss_2_print_vy_vec, loss_vy.item()]

        for x_batch_w, y_batch_w in minibatch_iter_w:
            optimizer_w.zero_grad()
            output_w = model_w(x_batch_w)
            loss_w = -mll_w(output_w, y_batch_w[:,0])
            minibatch_iter_w.set_postfix(loss=loss_w.item())
            loss_w.backward()
            optimizer_w.step()

        loss_2_print_w_vec = [*loss_2_print_w_vec, loss_w.item()]
           
    #plot loss functions
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.plot(loss_2_print_vx_vec,label='loss vx',color='dodgerblue') 
    ax.plot(loss_2_print_vy_vec,label='loss vy',color='orangered')
    ax.plot(loss_2_print_w_vec,label='loss w',color='orchid')
    ax.legend()


    #move to gpu for later evaluation
    model_vx = model_vx.cuda()
    model_vy = model_vy.cuda()
    model_w = model_w.cuda()

    return model_vx, model_vy, model_w, likelihood_vx, likelihood_vy, likelihood_w





#define orthogonally decoupled SVGP model
# Orthogonally decoupled SVGP
def make_orthogonal_vs(model,mean_inducing_points,covar_inducing_points):
    # mean_inducing_points = torch.randn(1000, train_x.size(-1), dtype=train_x.dtype, device=train_x.device)
    # covar_inducing_points = torch.randn(100, train_x.size(-1), dtype=train_x.dtype, device=train_x.device)

    covar_variational_strategy = gpytorch.variational.VariationalStrategy(
        model, covar_inducing_points,
        gpytorch.variational.CholeskyVariationalDistribution(covar_inducing_points.size(-2)),
        learn_inducing_locations=True
    )

    variational_strategy = gpytorch.variational.OrthogonallyDecoupledVariationalStrategy(
        covar_variational_strategy, mean_inducing_points,
        gpytorch.variational.DeltaVariationalDistribution(mean_inducing_points.size(-2)),
    )
    return variational_strategy

class OrthDecoupledApproximateGP(ApproximateGP):
    def __init__(self,mean_inducing_points,covar_inducing_points):
        #variational_distribution = gpytorch.variational.DeltaVariationalDistribution(inducing_points.size(-2))
        variational_strategy = make_orthogonal_vs(self,mean_inducing_points,covar_inducing_points)
        super().__init__(variational_strategy)
        self.mean_module = gpytorch.means.ZeroMean()
        self.covar_module =  gpytorch.kernels.ScaleKernel(gpytorch.kernels.RBFKernel(ard_num_dims=mean_inducing_points.size(dim=1)))

    def forward(self, x):
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)


def train_decoupled_SVGP_model(learning_rate,num_epochs, train_x, train_y_vx, train_y_vy, train_y_w, n_inducing_points_mean,n_inducing_points_cov):
    
    # start fitting
    # make contiguous (not sure why)
    train_x = train_x.contiguous()
    train_y_vx = train_y_vx.contiguous()
    train_y_vy = train_y_vy.contiguous()
    train_y_w = train_y_w.contiguous()

    # define batches for training (each bach will be used to perform a gradient descent step in each iteration. So toal parameters updates are Epochs*n_batches)
    from torch.utils.data import TensorDataset, DataLoader
    train_dataset_vx = TensorDataset(train_x, train_y_vx)
    train_dataset_vy = TensorDataset(train_x, train_y_vy)
    train_dataset_w = TensorDataset(train_x, train_y_w)

    # define data loaders
    train_loader_vx = DataLoader(train_dataset_vx, batch_size=250, shuffle=True)
    train_loader_vy = DataLoader(train_dataset_vy, batch_size=250, shuffle=True)
    train_loader_w = DataLoader(train_dataset_w, batch_size=250, shuffle=True)

    #choosing initial guess inducing points as a random subset of the training data
    random.seed(10) # set the seed so to have same points for every run
    # random selection of inducing points
    random_indexes_mean = random.choices(range(train_x.shape[0]), k=n_inducing_points_mean)
    inducing_points_mean = train_x[random_indexes_mean, :]
    inducing_points_mean = inducing_points_mean.to(torch.float32)

    random_indexes_cov = random.choices(range(inducing_points_mean.shape[0]), k=n_inducing_points_cov)
    inducing_points_cov = train_x[random_indexes_cov, :]


    #initialize models
    model_vx = OrthDecoupledApproximateGP(inducing_points_mean,inducing_points_cov)
    model_vy = OrthDecoupledApproximateGP(inducing_points_mean,inducing_points_cov)
    model_w = OrthDecoupledApproximateGP(inducing_points_mean,inducing_points_cov)


    # assign first guess lengthscales
    #                                                            vx, vy ,w, throttle,steer
    # model_vx.covar_module.base_kernel.lengthscale = torch.tensor([0.1,1,10,  0.1,    1])
    # model_vy.covar_module.base_kernel.lengthscale = torch.tensor([1,1,10,10,1])
    # model_w.covar_module.base_kernel.lengthscale =  torch.tensor([2,2,2,2,2])


    # Assign training data to models just to have it all together for later plotting
    model_vx.train_x = train_x 
    model_vx.train_y_vx = train_y_vx

    model_vy.train_x = train_x 
    model_vy.train_y_vy = train_y_vy

    model_w.train_x = train_x 
    model_w.train_y_w = train_y_w


    #define likelyhood objects
    likelihood_vx = gpytorch.likelihoods.GaussianLikelihood()
    likelihood_vy = gpytorch.likelihoods.GaussianLikelihood()
    likelihood_w = gpytorch.likelihoods.GaussianLikelihood()
 


    #move to GPU for faster fitting
    if torch.cuda.is_available():
        model_vx = model_vx.cuda()
        model_vy = model_vy.cuda()
        model_w = model_w.cuda()
        likelihood_vx = likelihood_vx.cuda()
        likelihood_vy = likelihood_vy.cuda()
        likelihood_w = likelihood_w.cuda()

    #set to training mode
    model_vx.train()
    model_vy.train()
    model_w.train()
    likelihood_vx.train()
    likelihood_vy.train()
    likelihood_w.train()

    #set up optimizer and its options
    optimizer_vx = torch.optim.AdamW([{'params': model_vx.parameters()}, {'params': likelihood_vx.parameters()},], lr=learning_rate)
    optimizer_vy = torch.optim.AdamW([{'params': model_vy.parameters()}, {'params': likelihood_vy.parameters()},], lr=learning_rate)
    optimizer_w = torch.optim.AdamW([{'params': model_w.parameters()}, {'params': likelihood_w.parameters()},], lr=learning_rate)


    # Set up loss object. We're using the VariationalELBO
    mll_vx = gpytorch.mlls.VariationalELBO(likelihood_vx, model_vx, num_data=train_y_vx.size(0))#, beta=1)
    mll_vy = gpytorch.mlls.VariationalELBO(likelihood_vy, model_vy, num_data=train_y_vy.size(0))#, beta=1)
    mll_w = gpytorch.mlls.VariationalELBO(likelihood_w, model_w, num_data=train_y_w.size(0))#, beta=1)

    # start training (tqdm is just to show the loading bar)
    epochs_iter = tqdm.tqdm(range(num_epochs), desc="Epoch")



    loss_2_print_vx_vec = []
    loss_2_print_vy_vec = []
    loss_2_print_w_vec = []

    for i in epochs_iter:
        # Within each iteration, we will go over each minibatch of data
        minibatch_iter_vx = tqdm.tqdm(train_loader_vx, desc="Minibatch vx", leave=False, disable=True)
        minibatch_iter_vy = tqdm.tqdm(train_loader_vy, desc="Minibatch vy", leave=False, disable=True)
        minibatch_iter_w  = tqdm.tqdm(train_loader_w,  desc="Minibatch w",  leave=False, disable=True)

        for x_batch_vx, y_batch_vx in minibatch_iter_vx:
            optimizer_vx.zero_grad()
            output_vx = model_vx(x_batch_vx)
            loss_vx = -mll_vx(output_vx, y_batch_vx[:,0])
            minibatch_iter_vx.set_postfix(loss=loss_vx.item())
            loss_vx.backward()
            optimizer_vx.step()

        loss_2_print_vx_vec = [*loss_2_print_vx_vec, loss_vx.item()]

        for x_batch_vy, y_batch_vy in minibatch_iter_vy:
            optimizer_vy.zero_grad()
            output_vy = model_vy(x_batch_vy)
            loss_vy = -mll_vy(output_vy, y_batch_vy[:,0])
            minibatch_iter_vy.set_postfix(loss=loss_vy.item())
            loss_vy.backward()
            optimizer_vy.step()

        loss_2_print_vy_vec = [*loss_2_print_vy_vec, loss_vy.item()]

        for x_batch_w, y_batch_w in minibatch_iter_w:
            optimizer_w.zero_grad()
            output_w = model_w(x_batch_w)
            loss_w = -mll_w(output_w, y_batch_w[:,0])
            minibatch_iter_w.set_postfix(loss=loss_w.item())
            loss_w.backward()
            optimizer_w.step()

        loss_2_print_w_vec = [*loss_2_print_w_vec, loss_w.item()]
           
    #plot loss functions
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.plot(loss_2_print_vx_vec,label='loss vx',color='dodgerblue') 
    ax.plot(loss_2_print_vy_vec,label='loss vy',color='orangered')
    ax.plot(loss_2_print_w_vec,label='loss w',color='orchid')
    ax.legend()


    #move to gpu for later evaluation
    model_vx = model_vx.cuda()
    model_vy = model_vy.cuda()
    model_w = model_w.cuda()

    return model_vx, model_vy, model_w, likelihood_vx, likelihood_vy, likelihood_w







class dyn_model_SVGP():
    def __init__(self,model_vx,model_vy,model_w):

        self.model_vx = model_vx
        self.model_vy = model_vy
        self.model_w = model_w

    def forward(self, state_action):
        input = torch.unsqueeze(torch.Tensor(state_action),0).cuda()
        ax= self.model_vx(input).mean.detach().cpu().numpy()[0]
        ay= self.model_vy(input).mean.detach().cpu().numpy()[0]
        aw= self.model_w(input).mean.detach().cpu().numpy()[0]

        return np.array([ax,ay,aw])
    
def rebuild_Kxy_RBF_vehicle_dynamics(X,Y,outputscale,lengthscale):
    n = X.shape[0]
    m = Y.shape[0]
    KXY = np.zeros((n,m))
    for i in range(n):
        for j in range(m):
            KXY[i,j] = RBF_kernel_rewritten(X[i,:],Y[j,:],outputscale,lengthscale)
    return KXY

def RBF_kernel_rewritten(x,y,outputscale,lengthscale):
    exp_arg = np.zeros(len(lengthscale))
    for i in range(len(lengthscale)):
        exp_arg[i] = (x[i]-y[i])**2/lengthscale[i]**2
    return outputscale * np.exp(-0.5*np.sum(exp_arg))

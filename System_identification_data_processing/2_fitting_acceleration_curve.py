from functions_for_data_processing import get_data, plot_raw_data, motor_curve_model
from matplotlib import pyplot as plt
import torch
import numpy as np
from scipy.interpolate import CubicSpline
import pandas as pd
from scipy.signal import savgol_filter
from scipy.interpolate import UnivariateSpline
# set font size for figures
import matplotlib
font = {'family' : 'normal',
        'size'   : 22}

matplotlib.rc('font', **font)



# this assumes that the current directory is DART
#folder_path = 'System_identification_data_processing/Data/2_step_input_data' 
#folder_path = 'System_identification_data_processing/Data/20_step_input_data_rubbery_floor' 
folder_path = 'System_identification_data_processing/Data/21_step_input_data_rubbery_floor_v_08-15' # velocity up to 1.5 m/s






# get the raw data
df_raw_data = get_data(folder_path)

# plot raw data
ax0,ax1,ax2 = plot_raw_data(df_raw_data)



# smooth velocity data
# ---------------------
# DO not use smoothed velocity data since the smoothed signal will have a delay and 
# a lead compared to the relative throttle signal and thus mess things up up.
# ---------------------

# Set the window size for the moving average
# window_size = 3#5
# poly_order = 1

# # Apply Savitzky-Golay filter
# smoothed_vel_encoder = savgol_filter(df_raw_data['vel encoder'].to_numpy(), window_size, poly_order)

# # v_spline = UnivariateSpline(df_raw_data['elapsed time sensors'].to_numpy(), df_raw_data['vel encoder'].to_numpy(), s=0.01)
# # smoothed_vel_encoder = v_spline(df_raw_data['elapsed time sensors'].to_numpy())

# ax1.plot(df_raw_data['elapsed time sensors'].to_numpy(),smoothed_vel_encoder,label="vel encoder smoothed",color='k',linestyle='--')
# ax1.legend()




# identify  delay
# ---------------------
# The delay we need to measure is between the throttlel and a change in velocity as measured by the data.
# indeed there seems to be no delay between the two signals
# ---------------------
#delay_th = 1 # [steps, i.e. 0.1s]

# process the raw data
m =1.67 #mass of the robot

# friction curve parameters from rubbery floor
a_friction =  1.5837167501449585
b_friction =  14.215554237365723
c_friction =  0.5013455152511597
d_friction =  -0.057962968945503235


# df = process_raw_data_acceleration(df_raw_data, delay_st)
df = df_raw_data[['elapsed time sensors','throttle','vel encoder']].copy() 

#df['vel encoder smoothed'] =  smoothed_vel_encoder # df_raw_data['vel encoder'] #non smoothed


# using raw velocity data
# ---------------------
# using FORWARD DIFFERENCE to compute the velocity is the best option because, as can be seen in the data,
# when the throttle is changed, the velocity SLOPE (i.e. the acceleration) changes from the next time step.
# ---------------------
# df['vel encoder'] = df_raw_data['vel encoder']
# spl_vel = CubicSpline(df['elapsed time sensors'].to_numpy(), df_raw_data['vel encoder'].to_numpy())  #df['vel encoder smoothed']
#df['force'] =   m * spl_vel(df['elapsed time sensors'].to_numpy(),1) # take the first derivative of the spline

acc = (df_raw_data['vel encoder'].to_numpy()[1:] - df_raw_data['vel encoder'].to_numpy()[:-1])/(df_raw_data['elapsed time sensors'].to_numpy()[1:]-df_raw_data['elapsed time sensors'].to_numpy()[:-1])
acc = np.append(acc , 0)# add a zero at the end to have the same length as the original data
df['force'] = m * acc 



df['friction force'] = + ( a_friction * np.tanh(b_friction  * df['vel encoder'] ) + c_friction * df['vel encoder'] + d_friction * df['vel encoder']**2)
df['motor force'] = df['force'] + df['friction force']


#adding delayed throttle signal
df['throttle prev1'] = np.append(0,df['throttle'].to_numpy()[:-1])
df['throttle prev2'] = np.append([0,0],df['throttle'].to_numpy()[:-2])
df['throttle prev3'] = np.append([0,0,0],df['throttle'].to_numpy()[:-3])
df['throttle prev4'] = np.append([0,0,0,0],df['throttle'].to_numpy()[:-4])
df['throttle prev5'] = np.append([0,0,0,0,0],df['throttle'].to_numpy()[:-5])




# plot velocity information against force

fig, ((ax3)) = plt.subplots(1, 1, figsize=(10, 6), constrained_layout=True)
fig.subplots_adjust(top=0.985, bottom=0.11, left=0.07, right=1.0, hspace=0.2, wspace=0.2)

ax3.set_title('velocity Vs motor force')
# velocity
ax3.plot(df['elapsed time sensors'].to_numpy(),df['vel encoder'].to_numpy(),label="velocity [m/s]",color='dodgerblue',linewidth=2,marker='.',markersize=10)

# throttle
ax3.step(df['elapsed time sensors'].to_numpy(),df['throttle'].to_numpy(),where='post',color='gray',linewidth=2,label="throttle")
ax3.plot(df['elapsed time sensors'].to_numpy(),df['throttle'].to_numpy(),color='gray',linewidth=2,marker='.',markersize=10,linestyle='none')

# measured acceleration
ax3.plot(df['elapsed time sensors'].to_numpy(),acc,color='darkgreen',linewidth=2,marker='.',markersize=10,linestyle='none')
ax3.step(df['elapsed time sensors'].to_numpy(),acc,label="acceleration",where='post',color='darkgreen',linewidth=2,linestyle='-')

# estimated friction force
ax3.step(df['elapsed time sensors'].to_numpy(),df['friction force'].to_numpy(),where='post',color='maroon',linewidth=2,label="estimated friction force [N]")
ax3.plot(df['elapsed time sensors'].to_numpy(),df['friction force'].to_numpy(),color='maroon',linewidth=2,marker='.',markersize=10,linestyle='none')

# estimated motor force
ax3.step(df['elapsed time sensors'].to_numpy(),df['motor force'].to_numpy(),where='post',color='k',linewidth=2,label="motor force [N]")
ax3.plot(df['elapsed time sensors'].to_numpy(),df['motor force'].to_numpy(),color='k',linewidth=2,marker='.',markersize=10,linestyle='none')



ax3.set_xlabel('time [s]')
ax3.set_title('Processed training data')






# --------------- fitting acceleration curve--------------- 
print('')
print('Fitting acceleration curve model')

# define first guess for parameters
initial_guess = torch.ones(4) * 0.5 # initialize parameters in the middle of their range constraint


# NOTE that the parmeter range constraint is set in motor_curve_model.transform_parameters_norm_2_real method.
n_past_throttle = 3
motor_curve_model_obj = motor_curve_model(initial_guess,n_past_throttle)

# define number of training iterations
normalize_output = False
train_its = 750

#define loss and optimizer objects
loss_fn = torch.nn.MSELoss(reduction = 'mean') 
optimizer_object = torch.optim.Adam(motor_curve_model_obj.parameters(), lr=0.003)
        
# generate data in tensor form for torch
train_x = torch.tensor(df[['throttle','vel encoder','throttle prev1','throttle prev2','throttle prev3','throttle prev4','throttle prev5']].to_numpy()).cuda()  
train_y = torch.unsqueeze(torch.tensor(df['motor force'].to_numpy()),1).cuda()

# save loss values for later plot
loss_vec = np.zeros(train_its)



# determine maximum value of training data for output normalization
if normalize_output:
    # Define a small threshold value
    threshold = 1e-6  # Adjust this value based on your needs
    max_y = train_y.max().item()
    rescale_vector = torch.Tensor(train_y.cpu().detach().numpy() / max_y).cuda()
    # Replace values that are close to zero with ones
    rescale_vector[rescale_vector.abs() < threshold] = 1
else:
    rescale_vector=torch.ones(train_y.shape[0]).cuda()


# train the model
for i in range(train_its):
    # clear gradient information from previous step before re-evaluating it for the current iteration
    optimizer_object.zero_grad()  
    
    # compute fitting outcome with current model parameters
    output = motor_curve_model_obj(train_x)

    # evaluate loss function
    loss = loss_fn(torch.div(output , rescale_vector),  torch.div(train_y , rescale_vector))
    loss_vec[i] = loss.item()

    # evaluate the gradient of the loss function with respect to the fitting parameters
    loss.backward() 

    # use the evaluated gradient to perform a gradient descent step 
    optimizer_object.step() # this updates parameters automatically according to the optimizer you chose

# --- print out parameters ---
[a,b,c,d] = motor_curve_model_obj.transform_parameters_norm_2_real()
a, b, c, d = a.item(), b.item(), c.item(), d.item()
print('a = ', a)
print('b = ', b)
print('c = ', c)
print('d = ', d)



# evalauting filter coefficient
k0 = d
k1 = d * (1-d)
k2 = d * (1-d)**2
k3 = d * (1-d)**3 
k4 = d * (1-d)**4 
k5 = d * (1-d)**5 


k_vec = np.array([k0,k1,k2,k3,k4,k5])
k_vec = k_vec[:n_past_throttle+1]
sum = np.sum(k_vec)
k_vec = k_vec/sum

# coefficients if k0 were used as a filter
c0 = k0/sum
c1 = k0/sum * (1-k0/sum)
c2 = k0/sum * (1-k0/sum) ** 2
c3 = k0/sum * (1-k0/sum) ** 3
c4 = k0/sum * (1-k0/sum) ** 4  
c5 = k0/sum * (1-k0/sum) ** 5
c_vec = np.array([c0,c1,c2,c3,c4,c5])
c_vec = c_vec[:n_past_throttle+1]

# Calculate the error
error = c_vec - k_vec

# Print out the error with 4 decimal places
print('filter coefficients')
for i in range(1+n_past_throttle):
    print(f"k_{i}: {k_vec[i]:.4f}")
print('')
# Print out the error with 4 decimal places
print('Error between coefficients and filter coefficients')
for i in range(1+n_past_throttle):
    print(f"Error at index {i}: {error[i]:.4f}")

#print ('coefficients = ',k0/sum,' ',k1/sum,' ',k2/sum)
#print('error between coeffiecients = ',k1/sum*(1-k1/sum)-k2/sum,' ',k1/sum*(1-k1/sum)**2-k3/sum)


# plot loss function
plt.figure()
plt.title('Loss')
plt.plot(loss_vec)
plt.xlabel('iterations')
plt.ylabel('loss')


#add predicted motor force to previous plot
ax3.step(df['elapsed time sensors'].to_numpy(),output.cpu().detach().numpy(),where='post',color='orangered',linewidth=2,label="estimated motor force")
ax3.plot(df['elapsed time sensors'].to_numpy(),output.cpu().detach().numpy(),color='orangered',linewidth=2,marker='.',markersize=10,linestyle='none')
ax3.legend()




#plot throttle signal and it's filtered version against the motor force. This is to se if we can capture the inductance dynamics in this way
# this is needed to set a first guess of what the filter should be
throttle_filtered = np.zeros(df['throttle'].shape[0])
alpha = k_vec[0] # set to a fixed value to set an initial guess for the fitting procedure

for i in range(1,df['throttle'].shape[0]):
    throttle_filtered[i] = (1 - alpha)*throttle_filtered[i-1] + alpha*df['throttle'].to_numpy()[i]
df['throttle filtered'] = throttle_filtered


# throttle filtered as in model
#throttle_weighted_average = np.zeros(df['throttle'].shape[0])
throttle_matrix = df[['throttle','throttle prev1','throttle prev2','throttle prev3','throttle prev4','throttle prev5']].to_numpy()
throttle_matrix = throttle_matrix[:,:n_past_throttle+1]

# for i in range(df['throttle'].shape[0]):
#     throttle_weighted_average[i] = 
throttle_weighted_average = throttle_matrix @ np.expand_dims(k_vec,1)


fig, ((ax4)) = plt.subplots(1, 1, figsize=(10, 6), constrained_layout=True)
fig.subplots_adjust(top=0.985, bottom=0.11, left=0.07, right=1.0, hspace=0.2, wspace=0.2)


# throttle
ax4.step(df['elapsed time sensors'].to_numpy(),df['throttle'].to_numpy(),where='post',color='gray',linewidth=2,label="throttle")
ax4.plot(df['elapsed time sensors'].to_numpy(),df['throttle'].to_numpy(),color='gray',linewidth=2,marker='.',markersize=10,linestyle='none')

# filtered throttle
ax4.step(df['elapsed time sensors'].to_numpy(),throttle_weighted_average,where='post',color='orangered',linewidth=2,label="throttle weighted")
ax4.plot(df['elapsed time sensors'].to_numpy(),throttle_weighted_average,color='orangered',linewidth=2,marker='.',markersize=10,linestyle='none')

# filtered throttle
ax4.step(df['elapsed time sensors'].to_numpy(),throttle_filtered,where='post',color='k',linewidth=2,label="throttle filtered",linestyle='--')
ax4.plot(df['elapsed time sensors'].to_numpy(),throttle_filtered,color='k',linewidth=2,marker='.',markersize=10,linestyle='none')


ax4.legend()


# add to the fitting results plot, the value of force using the filtered throttle
output_filtered_throttle = motor_curve_model_obj.motor_equation(torch.Tensor(throttle_filtered).cuda(),train_x[:,1]).detach().cpu().view(-1).numpy()
ax3.step(df['elapsed time sensors'].to_numpy(),output_filtered_throttle,where='post',color='red',linewidth=2,label="estimated motor force filtered throttle")
ax3.plot(df['elapsed time sensors'].to_numpy(),output_filtered_throttle,color='red',linewidth=2,marker='.',markersize=10,linestyle='none')
ax3.legend()





# --- plot motor curve ---
from mpl_toolkits.mplot3d import Axes3D
fig = plt.figure(figsize=(8, 6))
ax = fig.add_subplot(111, projection='3d')
x = throttle_weighted_average #train_x[:,0].cpu().detach().numpy()
y = train_x[:,1].cpu().detach().numpy()
z = train_y.cpu().detach().numpy()
ax.scatter(x, y, z, c='b', marker='o')


# Create a meshgrid for the surface plot

# find maximum value of velocity
v_max = 5 #a/b

throttle_range = np.linspace(0, max(x), 100)
velocity_rage = np.linspace(0, v_max, 100)
throttle_grid, velocity_grid = np.meshgrid(throttle_range, velocity_rage)
# Create input points
input_points = np.column_stack(
    (
        throttle_grid.flatten(),
        velocity_grid.flatten(),
    )
)

input_grid = torch.tensor(input_points, dtype=torch.float32).cuda()
Force_grid = motor_curve_model_obj.motor_equation(input_grid[:,0],input_grid[:,1]).detach().cpu().view(100, 100).numpy()  # Replace with your surface data

# Plot the surface
ax.plot_surface(throttle_grid, velocity_grid, Force_grid, cmap='viridis', alpha=1)
# Set labels
ax.set_xlabel('throttle')
ax.set_ylabel('velocity')
ax.set_zlabel('Motor force')

# plotting the obtained motor curve as a level plot
max_throttle = df['throttle'].max()
throttle_levels = np.linspace(-c,max_throttle,5).tolist()  # 0.4 set throttle

fig = plt.figure(figsize=(10, 6))
fig.subplots_adjust(top=0.985, bottom=0.11, left=0.07, right=1.0, hspace=0.2, wspace=0.2)

#heatmap = plt.imshow(throttle_grid, extent=[velocity_grid.min(), Force_grid.max(), Force_grid.min(), throttle_grid.max()], origin='lower', cmap='plasma')
contour1 = plt.contourf(velocity_grid, Force_grid ,throttle_grid, levels=100, cmap='plasma') 
contour2 = plt.contour(velocity_grid, Force_grid ,throttle_grid, levels=throttle_levels, colors='black', linestyles='solid', linewidths=2) 
cbar = plt.colorbar(contour1, label='Throttle',ticks=[0, *throttle_levels, 1],format='%.2f')

# from matplotlib.ticker import StrMethodFormatter
# cbar.ax.yaxis.set_major_formatter(StrMethodFormatter('{x:,.2f}'))
# cbar.set_ticks([0, *throttle_levels, 1])

#cbar.update_ticks()
# Add labels for contour lines
plt.clabel(contour2, inline=True, fontsize=18, fmt='%1.2f')
# Set labels
plt.xlabel('Velocity [m/s]')
plt.ylabel('Force [N]')

df_data = df[df['vel encoder']>1]
df_data = df_data[df_data['vel encoder']<3]
vel_data = df_data['vel encoder'][df_data['throttle']==0.4000000059604645].to_numpy()
mot_force_data = df_data['motor force'][df_data['throttle']==0.4000000059604645].to_numpy()
plt.scatter(vel_data,mot_force_data,color='k',label='data for throttle = 0.4')
plt.legend()











#plot error between model and data
fig = plt.figure(figsize=(8, 6))
ax = fig.add_subplot(111, projection='3d')
z = output.cpu().detach().numpy() - train_y.cpu().detach().numpy()
flat_x = x.flatten()
flat_y = y.flatten()    
flat_z = z.flatten()
mask = flat_x >= 0.1
flat_x = flat_x[mask]
flat_y = flat_y[mask]
flat_z = flat_z[mask]

max_val_plot = np.max([np.abs(np.min(flat_z)),np.max(flat_z)])
max_val_plot = 3
from matplotlib.colors import Normalize
norm = Normalize(vmin=-max_val_plot, vmax=max_val_plot)


scatter =  ax.scatter(flat_x, flat_y, flat_z, c=flat_z.flatten(), cmap='bwr', marker='o',norm=norm)
# Add a color bar to show the color scale
cbar = fig.colorbar(scatter, ax=ax)
cbar.set_label('Z value')
#ax.set_xlim([0.2,0.4])
ax.set_xlabel('throttle')
ax.set_ylabel('velocity')
plt.show()






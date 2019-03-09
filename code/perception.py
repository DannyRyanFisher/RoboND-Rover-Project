import numpy as np
import cv2

# Identify pixels above the threshold
# Threshold of RGB > 160 does a nice job of identifying ground pixels only
def color_thresh(img, rgb_thresh=(160, 160, 160)):
    # Create an array of zeros same xy size as img, but single channel
    color_select = np.zeros_like(img[:,:,0])
    # Require that each pixel be above all three threshold values in RGB
    # above_thresh will now contain a boolean array with "True"
    # where threshold was met
    above_thresh = (img[:,:,0] > rgb_thresh[0]) \
                & (img[:,:,1] > rgb_thresh[1]) \
                & (img[:,:,2] > rgb_thresh[2])
    # Index the array of zeros with the boolean array and set to 1
    color_select[above_thresh] = 1
    # Return the binary image
    return color_select

def find_rocks(img, rgb_thresh=(110,110,50)):
    # Create an array of zeros same xy size as img, but single channel
    color_select = np.zeros_like(img[:,:,0])
    above_thresh = (img[:,:,0] > rgb_thresh[0]) \
                & (img[:,:,1] > rgb_thresh[1]) \
                & (img[:,:,2] < rgb_thresh[2])
    # Index the array of zeros with the boolean array and set to 1
    color_select[above_thresh] = 1
    # Return the binary image
    return color_select

def apply_ellipse_mask(img,center,axes,angle,startAngle,endAngle):
    # Make single img filled with zeros
    mask=np.zeros_like(img[:,:,0])
    # Note: 1 means color=1 (white), -1 means fill ellipse
    cv2.ellipse(mask, center, axes, angle, startAngle, endAngle,1,-1);
    #3. Use a bitwise_and for selecting the region of interest (RoI)
    img2 = cv2.bitwise_and(img,img,mask=mask)
    return img2, mask

# Define a function to convert from image coords to rover coords
def rover_coords(binary_img):
    # Identify nonzero pixels
    ypos, xpos = binary_img.nonzero()
    # Calculate pixel positions with reference to the rover position being at the 
    # center bottom of the image.  
    x_pixel = -(ypos - binary_img.shape[0]).astype(np.float)
    y_pixel = -(xpos - binary_img.shape[1]/2 ).astype(np.float)
    return x_pixel, y_pixel


# Define a function to convert to radial coords in rover space
def to_polar_coords(x_pixel, y_pixel):
    # Convert (x_pixel, y_pixel) to (distance, angle) 
    # in polar coordinates in rover space
    # Calculate distance to each pixel
    dist = np.sqrt(x_pixel**2 + y_pixel**2)
    # Calculate angle away from vertical for each pixel
    angles = np.arctan2(y_pixel, x_pixel)
    return dist, angles

# Define a function to map rover space pixels to world space
def rotate_pix(xpix, ypix, yaw):
    # Convert yaw to radians
    yaw_rad = yaw * np.pi / 180
    xpix_rotated = (xpix * np.cos(yaw_rad)) - (ypix * np.sin(yaw_rad))

    ypix_rotated = (xpix * np.sin(yaw_rad)) + (ypix * np.cos(yaw_rad))
    # Return the result  
    return xpix_rotated, ypix_rotated

def translate_pix(xpix_rot, ypix_rot, xpos, ypos, scale): 
    # Apply a scaling and a translation
    xpix_translated = (xpix_rot / scale) + xpos
    ypix_translated = (ypix_rot / scale) + ypos
    # Return the result  
    return xpix_translated, ypix_translated


# Define a function to apply rotation and translation (and clipping)
# Once you define the two functions above this function should work
def pix_to_world(xpix, ypix, xpos, ypos, yaw, world_size, scale):
    # Apply rotation
    xpix_rot, ypix_rot = rotate_pix(xpix, ypix, yaw)
    # Apply translation
    xpix_tran, ypix_tran = translate_pix(xpix_rot, ypix_rot, xpos, ypos, scale)
    # Perform rotation, translation and clipping all at once
    x_pix_world = np.clip(np.int_(xpix_tran), 0, world_size - 1)
    y_pix_world = np.clip(np.int_(ypix_tran), 0, world_size - 1)
    # Return the result
    return x_pix_world, y_pix_world

def perspect_transform(img, src, dst):

    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (img.shape[1], img.shape[0]))# keep same size as input image
    mask = cv2.warpPerspective(np.ones_like(img[:,:,0]), M, (img.shape[1], img.shape[0]))
    return warped, mask


# Apply the above functions in succession and update the Rover state accordingly
def perception_step(Rover):

    # Perform perception steps to update Rover()
    # NOTE: camera image is coming to you in Rover.img
    img = Rover.img
    # 1) Define source and destination points for perspective transform
    dst_size = 5
    bottom_offset = 6
    source = np.float32([[14, 140], [301 ,140],[200, 96], [118, 96]])
    destination = np.float32([[img.shape[1]/2 - dst_size, img.shape[0] - bottom_offset],
                  [img.shape[1]/2 + dst_size, img.shape[0] - bottom_offset],
                  [img.shape[1]/2 + dst_size, img.shape[0] - 2*dst_size - bottom_offset], 
                  [img.shape[1]/2 - dst_size, img.shape[0] - 2*dst_size - bottom_offset],
                  ])
    world_size = Rover.worldmap.shape[0]
    scale = 2 * dst_size
    # Update rover telemetry
    rover_xpos = Rover.pos[0]
    rover_ypos = Rover.pos[1]
    rover_yaw  = Rover.yaw

    # 2) Apply perspective transform
    warped, maskFOV = perspect_transform(img, source, destination)

    # Some others values needed for masks
    center=(160,155)
    radius=110
    axes = (radius,radius);
    angle=0;
    startAngle=180;
    endAngle=360;

    # Apply ellipse mask
    warpedThrash, mask_circle = apply_ellipse_mask(warped,center,axes,angle,startAngle,endAngle)

    # 3) Apply color threshold to identify navigable terrain/obstacles/rock samples
    navigableMap  = color_thresh(warped) * mask_circle

    # Using hint, just the inverse image
    obstaclesMap = np.absolute(np.float32(navigableMap)-1) * maskFOV * mask_circle
    # Rocks
    rocksMap = find_rocks(warped) * mask_circle


    # 4) Update Rover.vision_image (this will be displayed on left side of screen)

    Rover.vision_image[:,:,0] = obstaclesMap *255
    Rover.vision_image[:,:,1] = rocksMap * 255
    Rover.vision_image[:,:,2] = navigableMap* 255

    # 5) Convert map image pixel values to rover-centric coords
    navXpix , navYpix = rover_coords(navigableMap)
    obsXpix , obsYpix = rover_coords(obstaclesMap)
    rocXpix , rocYpix = rover_coords(rocksMap)

    # 6) Convert rover-centric pixel values to world coordinates

    # Get navigable pixel positions in world coords
    x_world_nav, y_world_nav = pix_to_world(navXpix, navYpix,
                                            rover_xpos,rover_ypos,rover_yaw,
                                            world_size,scale)

    # Get obstacle pixel positions in world coords
    x_world_obstacle, y_world_obstacle = pix_to_world(obsXpix, obsYpix,
                                                      rover_xpos,rover_ypos,rover_yaw,
                                                      world_size, scale)

    # Get rock pixel positions in world coords
    x_world_rock, y_world_rock = pix_to_world(rocXpix, rocYpix,
                                              rover_xpos, rover_ypos, rover_yaw,
                                              world_size, scale) 

    # 7) Update Rover worldmap (to be displayed on right side of screen)

    #Updating the map when roll and pitch are very low
    if (Rover.pitch < 1.5 or Rover.pitch > 359) and (Rover.roll < 1.5 or Rover.roll > 358.5):
        Rover.worldmap[y_world_nav,x_world_nav, 2] = 255
        Rover.worldmap[y_world_obstacle, x_world_obstacle, 0] = 255
        Rover.worldmap[y_world_rock, x_world_rock, 1] = 255

    # 8) Convert rover-centric pixel positions to polar coordinates
    # Update Rover pixel distances and angles

    Rover.nav_dist , Rover.nav_angles = to_polar_coords(navXpix , navYpix)
    Rover.obs_dist , Rover.obs_angles = to_polar_coords(obsXpix , obsYpix)
    Rover.rock_dist , Rover.rock_angles = to_polar_coords(rocXpix , rocYpix)



    return Rover


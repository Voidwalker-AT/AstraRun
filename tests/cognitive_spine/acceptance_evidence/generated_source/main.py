import os
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def generate_3d_plot(func, x_range, y_range, resolution=100):
    """
    Generates a 3D plot of a given function over a specified range.
    
    Parameters:
    func (callable): The function to plot. It should take two arguments (x, y) and return a scalar value.
    x_range (tuple): The range of x values to plot.
    y_range (tuple): The range of y values to plot.
    resolution (int): The number of points to use for each dimension.
    
    Returns:
    None
    """
    x = np.linspace(x_range[0], x_range[1], resolution)
    y = np.linspace(y_range[0], y_range[1], resolution)
    X, Y = np.meshgrid(x, y)
    Z = func(X, Y)
    
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.plot_surface(X, Y, Z, cmap='viridis')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    plt.title('3D Visualization of the Function')
    plt.show()

def main():
    # Choose a function to plot
    func = lambda x, y: np.sin(np.sqrt(x**2 + y**2)) / (np.sqrt(x**2 + y**2) + 1e-6)
    
    # Define the range of x and y
    x_range = (-5, 5)
    y_range = (-5, 5)
    
    # Generate the 3D plot
    generate_3d_plot(func, x_range, y_range)

if __name__ == "__main__":
    main()
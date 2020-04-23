#  -*- coding: utf-8 -*-

""" Functions for pivot calibration. """

import random
import numpy as np

def pivot_calibration(tracking_matrices, configuration=None):
    """
    Performs pivot calibration on an array of tracking matrices

    :param tracking_matrices: an Nx4x4 array of tracking matrices
    :param configuration: an optional configuration dictionary, if not
        the algorithm defaults to Algebraic One Step. Other options
        include ransac

    :returns: tuple containing;
            'pointer_offset' The coordinate of the pointer tip relative to
            the tracking centre
            'pivot_point' The location of the pivot point in world coordinates
            'residual_error' A measure of the residual calibration error

    :raises: TypeError, ValueError
    """

    if not isinstance(tracking_matrices, np.ndarray):
        raise TypeError("tracking_matrices is not a numpy array'")

    if not tracking_matrices.shape[1] == 4:
        raise ValueError("tracking_matrices should have 4 rows per matrix")

    if not tracking_matrices.shape[2] == 4:
        raise ValueError("tracking_matrices should have 4 columns per matrix")

    use_algebraic_one_step = False
    use_ransac = False

    if configuration is not None:
        use_algebraic_one_step = False
        method = configuration.get('method', 'aos')
        if method == 'aos':
            use_algebraic_one_step = True
        elif method == 'ransac':
            use_ransac = True
    else:
        use_algebraic_one_step = True

    if use_algebraic_one_step:
        return pivot_calibration_aos(tracking_matrices)

    if use_ransac:
        number_iterations = configuration.get('number_iterations', 10)
        error_threshold = configuration.get('error_threshold', 4)
        consensus_threshold = configuration.get('consensus_threshold',
                                                0.25)
        early_exit = configuration.get('early_exit', False)
        return pivot_calibration_with_ransac(
            tracking_matrices, number_iterations, error_threshold,
            consensus_threshold, early_exit)

    raise ValueError("method key set to unknown method; ",
                     configuration.get('method', 'aos'))

def pivot_calibration_aos(tracking_matrices):

    """
    Performs Pivot Calibration, using Algebraic One Step method,
    and returns Residual Error.

    See `Yaniv 2015 <https://dx.doi.org/10.1117/12.2081348>`_.

    :param tracking_matrices: N x 4 x 4 ndarray, of tracking matrices.
    :returns: pointer offset, pivot point and RMS Error about centroid of pivot.
    :raises: ValueError if rank less than 6
    """
    number_of_matrices = tracking_matrices.shape[0]

    # See equation in section 2.1.2 of Yaniv 2015.
    # Ax = b.

    size_a = 3 * number_of_matrices, 3
    # A contains rotation matrix from each tracking matrix.
    # and -I for each tracking matrix.
    a_first = (tracking_matrices [:, 0:3, 0:3]).reshape(size_a)
    a_second = (np.eye(3) * -1.0).reshape((1, 3, 3)).repeat(
        number_of_matrices, 0).reshape(size_a)
    a_values = np.concatenate((a_first, a_second), axis=1)

    # Column vector containing -1 * translation from each tracking matrix.
    size_b = 3 * number_of_matrices, 1
    b_values = (tracking_matrices[:, 0:3, 3] * -1.0).reshape((size_b))

    # To calculate Singular Value Decomposition

    u_values, s_values, v_values = np.linalg.svd(a_values, full_matrices=False)
    c_values = np.dot(u_values.T, b_values)
    w_values = np.dot(np.diag(1 / s_values), c_values)
    x_values = np.dot(v_values.T, w_values)

    # Calculating the rank, and removing close to zero singular values.
    rank = replace_small_values(s_values, 0.01, 0.0)

    if rank < 6:
        raise ValueError("PivotCalibration: Failed. Rank < 6")

    pointer_offset = x_values[0:3]
    pivot_location = x_values[3:6]
    # Compute RMS error.
    residual_matrix = (np.dot(a_values, x_values) - b_values)
    residual_error = np.sum(residual_matrix * residual_matrix)
    residual_error = residual_error / float(number_of_matrices * 3)
    residual_error = np.sqrt(residual_error)

    return pointer_offset, pivot_location, residual_error


def replace_small_values(the_list, threshold=0.01, replacement_value=0.0):
    """
    replace small values in a list, this changes the list in place.

    :param the_list: the list to process.
    :param theshold: replace values lower than threshold.
    :param replacement_value: value to replace with.
    :returns: the number of items not replaced.
    """
    rank = 0
    for index, item in enumerate(the_list):
        if item < threshold:
            the_list[index] = replacement_value
        else:
            rank += 1

    return rank


def pivot_calibration_with_ransac(tracking_matrices,
                                  number_iterations,
                                  error_threshold,
                                  concensus_threshold,
                                  early_exit=False
                                  ):
    """
    Written as an exercise for implementing RANSAC.

    :param tracking_matrices: N x 4 x 4 ndarray, of tracking matrices.
    :param number_iterations: the number of iterations to attempt.
    :param error_threshold: distance in millimetres from pointer position
    :param concensus_threshold: the minimum percentage of inliers to finish
    :param early_exit: If True, returns model as soon as thresholds are met
    :returns: pointer offset, pivot point and RMS Error about centroid of pivot.
    :raises: TypeError, ValueError
    """
    if number_iterations < 1:
        raise ValueError("The number of iterations must be > 1")
    if error_threshold < 0:
        raise ValueError("The error threshold must be a positive distance.")
    if concensus_threshold < 0 or concensus_threshold > 1:
        raise ValueError("The concensus threshold must be [0-1] as percentage")
    if not isinstance(tracking_matrices, np.ndarray):
        raise TypeError("tracking_matrices is not a numpy array'")

    number_of_matrices = tracking_matrices.shape[0]
    population_of_indices = range(number_of_matrices)
    minimum_matrices_required = 3

    highest_number_of_inliers = -1
    best_pointer_offset = None
    best_pivot_location = None
    best_residual_error = -1

    for iter_counter in range(number_iterations):
        indexes = random.sample(population_of_indices,
                                minimum_matrices_required)
        sample = tracking_matrices[indexes]

        try:
            pointer_offset, pivot_location, _ = pivot_calibration(sample)
        except ValueError:
            print("RANSAC, iteration " + str(iter_counter) + ", failed.")
            continue

        # Need to evaluate the number of inliers.
        # Slow, but it's written as a teaching exercise.
        number_of_inliers = 0
        inlier_indices = []
        for matrix_counter in range(number_of_matrices):
            offset = np.vstack((pointer_offset, 1))
            transformed_point = tracking_matrices[matrix_counter] @ offset
            diff = pivot_location - transformed_point[0:3]
            norm = np.linalg.norm(diff)
            if norm < error_threshold:
                number_of_inliers = number_of_inliers + 1
                inlier_indices.append(matrix_counter)

        percentage_inliers = number_of_inliers / number_of_matrices

        # Keep the best model so far, based on the highest number of inliers.
        if percentage_inliers > concensus_threshold \
                and number_of_inliers > highest_number_of_inliers:
            highest_number_of_inliers = number_of_inliers
            inlier_matrices = tracking_matrices[inlier_indices]
            best_pointer_offset, best_pivot_location, best_residual_error = \
                pivot_calibration(inlier_matrices)

        # Early exit condition, as soon as we find model with enough fit.
        if percentage_inliers > concensus_threshold and early_exit:
            return best_pointer_offset, best_pivot_location, best_residual_error

    if best_pointer_offset is None:
        raise ValueError("Failed to find a model using RANSAC.")

    print("RANSAC Pivot, from " + str(number_of_matrices)
          + " matrices, used " + str(highest_number_of_inliers)
          + " matrices, with error threshold = " + str(error_threshold)
          + " and consensus threshold = " + str(concensus_threshold)
          )

    return best_pointer_offset, best_pivot_location, best_residual_error
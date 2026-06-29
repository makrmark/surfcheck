def calculate_embayment_factor(wave_height, wave_period, beach_aspect, left_offset, right_offset):
    """Calculate the embayment factor based on beach width and wave size."""
    beach_width = (left_offset + right_offset) * 100  # Convert degrees to meters (approximate)
    wave_length = 1.56 * wave_period  # Approximate wavelength in meters
    if wave_period < 6:
        return 0.0
    else:
        return eff_height * (wave_period / 10)  # Simplified embayment factor
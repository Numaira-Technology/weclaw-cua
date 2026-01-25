"""
Human-like mouse movement using bezier curves and spline interpolation.

Generates natural cursor trajectories that mimic human behavior with:
- Bezier curve path generation for smooth curves
- Randomized control points for natural variance
- Speed variation with acceleration/deceleration
- Optional zigzag patterns for more realistic movement

Usage:
    from computer_server.utils.human_mouse import HumanMouseMover
    
    mover = HumanMouseMover()
    # Generate path from current position to target
    path = mover.generate_path(start_x, start_y, end_x, end_y)
    # Move along the path
    for x, y in path:
        mouse.position = (x, y)
        time.sleep(mover.get_step_delay())

Input:
    start_x, start_y: Starting coordinates
    end_x, end_y: Target coordinates
    speed_factor: Movement speed multiplier (lower = faster)
    
Output:
    List of (x, y) coordinate tuples forming a smooth path
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class HumanMouseConfig:
    """Configuration for human-like mouse movement."""
    
    enabled: bool = True
    speed_factor: float = 1.0
    min_steps: int = 10
    max_steps: int = 100
    curve_variance: float = 0.3
    zigzag_enabled: bool = False
    zigzag_amplitude: float = 5.0
    base_delay_ms: float = 5.0


class HumanMouseMover:
    """Generates human-like mouse movement paths using bezier curves."""
    
    def __init__(self, config: HumanMouseConfig = None):
        self.config = config or HumanMouseConfig()
        self._last_move_time = 0.0
    
    def generate_path(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        speed_factor: float = None,
    ) -> List[Tuple[int, int]]:
        """Generate a human-like path from start to end coordinates.
        
        Uses cubic bezier curves with randomized control points to create
        natural-looking cursor trajectories.
        
        Args:
            start_x: Starting X coordinate
            start_y: Starting Y coordinate
            end_x: Target X coordinate
            end_y: Target Y coordinate
            speed_factor: Optional override for movement speed
            
        Returns:
            List of (x, y) integer coordinate tuples
        """
        if not self.config.enabled:
            return [(int(end_x), int(end_y))]
        
        speed = speed_factor if speed_factor is not None else self.config.speed_factor
        
        distance = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)
        
        if distance < 5:
            return [(int(end_x), int(end_y))]
        
        num_steps = self._calculate_steps(distance, speed)
        control_points = self._generate_control_points(
            start_x, start_y, end_x, end_y, distance
        )
        path = self._bezier_curve(control_points, num_steps)
        
        if self.config.zigzag_enabled:
            path = self._apply_zigzag(path)
        
        path = self._apply_noise(path)
        path.append((int(end_x), int(end_y)))
        
        return path
    
    def _calculate_steps(self, distance: float, speed_factor: float) -> int:
        """Calculate number of steps based on distance and speed."""
        base_steps = int(distance / 10)
        steps = int(base_steps * speed_factor)
        steps = max(self.config.min_steps, min(steps, self.config.max_steps))
        steps += random.randint(-3, 3)
        return max(self.config.min_steps, steps)
    
    def _generate_control_points(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        distance: float,
    ) -> List[Tuple[float, float]]:
        """Generate bezier curve control points with natural variance."""
        mid_x = (start_x + end_x) / 2
        mid_y = (start_y + end_y) / 2
        
        variance = distance * self.config.curve_variance
        
        dx = end_x - start_x
        dy = end_y - start_y
        
        perp_x = -dy
        perp_y = dx
        length = math.sqrt(perp_x ** 2 + perp_y ** 2)
        if length > 0:
            perp_x /= length
            perp_y /= length
        
        offset1 = random.uniform(-variance, variance)
        offset2 = random.uniform(-variance, variance)
        
        ctrl1_x = start_x + dx * 0.25 + perp_x * offset1
        ctrl1_y = start_y + dy * 0.25 + perp_y * offset1
        
        ctrl2_x = start_x + dx * 0.75 + perp_x * offset2
        ctrl2_y = start_y + dy * 0.75 + perp_y * offset2
        
        return [
            (start_x, start_y),
            (ctrl1_x, ctrl1_y),
            (ctrl2_x, ctrl2_y),
            (end_x, end_y),
        ]
    
    def _bezier_curve(
        self,
        control_points: List[Tuple[float, float]],
        num_steps: int,
    ) -> List[Tuple[int, int]]:
        """Generate points along a cubic bezier curve."""
        path = []
        p0, p1, p2, p3 = control_points
        
        for i in range(num_steps):
            t = self._ease_in_out(i / num_steps)
            
            x = (
                (1 - t) ** 3 * p0[0]
                + 3 * (1 - t) ** 2 * t * p1[0]
                + 3 * (1 - t) * t ** 2 * p2[0]
                + t ** 3 * p3[0]
            )
            y = (
                (1 - t) ** 3 * p0[1]
                + 3 * (1 - t) ** 2 * t * p1[1]
                + 3 * (1 - t) * t ** 2 * p2[1]
                + t ** 3 * p3[1]
            )
            
            path.append((int(x), int(y)))
        
        return path
    
    def _ease_in_out(self, t: float) -> float:
        """Apply ease-in-out timing function for natural acceleration."""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2
    
    def _apply_zigzag(self, path: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Apply subtle zigzag pattern to the path."""
        if len(path) < 3:
            return path
        
        result = [path[0]]
        amplitude = self.config.zigzag_amplitude
        
        for i in range(1, len(path) - 1):
            x, y = path[i]
            
            if i > 0 and i < len(path) - 1:
                dx = path[i + 1][0] - path[i - 1][0]
                dy = path[i + 1][1] - path[i - 1][1]
                length = math.sqrt(dx ** 2 + dy ** 2)
                
                if length > 0:
                    perp_x = -dy / length
                    perp_y = dx / length
                    
                    offset = math.sin(i * 0.5) * amplitude * random.uniform(0.5, 1.0)
                    x += int(perp_x * offset)
                    y += int(perp_y * offset)
            
            result.append((x, y))
        
        result.append(path[-1])
        return result
    
    def _apply_noise(self, path: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Apply small random noise to make movement more natural."""
        result = []
        
        for i, (x, y) in enumerate(path):
            if i == 0 or i == len(path) - 1:
                result.append((x, y))
            else:
                noise_x = random.randint(-1, 1)
                noise_y = random.randint(-1, 1)
                result.append((x + noise_x, y + noise_y))
        
        return result
    
    def get_step_delay(self, step_index: int = 0, total_steps: int = 1) -> float:
        """Calculate delay between movement steps.
        
        Varies delay to simulate natural human speed variation.
        """
        base_delay = self.config.base_delay_ms / 1000.0
        
        progress = step_index / max(total_steps, 1)
        if progress < 0.2:
            multiplier = 1.5 - progress * 2.5
        elif progress > 0.8:
            multiplier = 0.5 + (progress - 0.8) * 2.5
        else:
            multiplier = 1.0
        
        variance = random.uniform(0.8, 1.2)
        
        return base_delay * multiplier * variance * self.config.speed_factor


async def move_mouse_human(
    mouse_controller,
    target_x: int,
    target_y: int,
    config: HumanMouseConfig = None,
    speed_factor: float = None,
) -> None:
    """Move mouse to target coordinates with human-like motion.
    
    Args:
        mouse_controller: pynput mouse controller instance
        target_x: Target X coordinate
        target_y: Target Y coordinate
        config: Optional HumanMouseConfig instance
        speed_factor: Optional speed override (lower = faster)
    """
    import asyncio
    
    config = config or HumanMouseConfig()
    mover = HumanMouseMover(config)
    
    current_x, current_y = mouse_controller.position
    
    path = mover.generate_path(
        current_x, current_y,
        target_x, target_y,
        speed_factor=speed_factor,
    )
    
    total_steps = len(path)
    for i, (x, y) in enumerate(path):
        mouse_controller.position = (x, y)
        delay = mover.get_step_delay(i, total_steps)
        await asyncio.sleep(delay)


def move_mouse_human_sync(
    mouse_controller,
    target_x: int,
    target_y: int,
    config: HumanMouseConfig = None,
    speed_factor: float = None,
) -> None:
    """Synchronous version of move_mouse_human.
    
    Args:
        mouse_controller: pynput mouse controller instance
        target_x: Target X coordinate
        target_y: Target Y coordinate
        config: Optional HumanMouseConfig instance
        speed_factor: Optional speed override (lower = faster)
    """
    config = config or HumanMouseConfig()
    mover = HumanMouseMover(config)
    
    current_x, current_y = mouse_controller.position
    
    path = mover.generate_path(
        current_x, current_y,
        target_x, target_y,
        speed_factor=speed_factor,
    )
    
    total_steps = len(path)
    for i, (x, y) in enumerate(path):
        mouse_controller.position = (x, y)
        delay = mover.get_step_delay(i, total_steps)
        time.sleep(delay)

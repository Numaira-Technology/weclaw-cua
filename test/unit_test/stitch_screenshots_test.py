from pathlib import Path
from algorithm_a.stitch_screenshots import stitch_screenshots

TEST_DIR = Path(__file__).resolve().parents[1]
TEST_DATA_DIR = TEST_DIR / "test_data"
TEST_OUTPUT_DIR = TEST_DIR / "test_data_output"

def test_stitch_screenshots():
    screenshot_paths = generate_screenshot_paths()
    TEST_OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = TEST_OUTPUT_DIR / "stitched_screenshot.png"
    stitch_screenshots(screenshot_paths, output_path)

def generate_screenshot_paths():
    return sorted(TEST_DATA_DIR.glob("*.png"))


if __name__ == "__main__":
    test_stitch_screenshots()
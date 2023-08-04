from testConfig import TestConfig
from trafficFlowTests import TrafficFlowTests
import arguments


def main():
    print("START HERE")
    args = arguments.parse_args()
    cc = TestConfig(args.config)
    tft = TrafficFlowTests(cc)
    tft.run()

    print("END HERE")

if __name__ == "__main__":
    main()

from testConfig import TestConfig
from trafficFlowTests import TrafficFlowTests


def main():
    print("START HERE")
    cc = TestConfig()
    tft = TrafficFlowTests(cc)
    tft.run()

    print("END HERE")

if __name__ == "__main__":
    main()

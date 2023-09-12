from testConfig import TestConfig
from trafficFlowTests import TrafficFlowTests
import arguments
import sys
from evaluator import Status


def main():
    print("START HERE")
    args = arguments.parse_args()
    cc = TestConfig(args.config)
    tft = TrafficFlowTests(cc)

    results = []
    for test in tft._tft.GetConfig():
        try:
            results.append(tft.run(test, args.evaluator_config))
        except Exception as e:
            print(f"Error occured while running following test:\n {test}")
            print(f"Test failed with exception: {e}")
            results.append(Status(False, 0, 0))

    all_passing = True
    for status in results:
        print(f"RESULT: Success = {status.result}. Passed {status.num_passed}/{status.num_passed + status.num_failed}")
        if not status.result:
            all_passing = False

    if not all_passing:
        sys.exit(-1)

if __name__ == "__main__":
    main()

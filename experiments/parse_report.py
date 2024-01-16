import os

import yaml

if __name__ == "__main__":
    # report_folder = "./report/trail_01_15_01_48_02" # 3
    # report_folder = "./report/trail_01_15_05_14_43" # 4
    report_folder = "./report/trail_01_15_10_09_35"  # 5

    result = {
        "pre_opt": {"service_time": [], "tail_latency": [], "cpu_usage": []},
        "post_opt": {"service_time": [], "tail_latency": [], "cpu_usage": []},
    }

    for filename in os.listdir(report_folder):
        file_path = os.path.join(report_folder, filename)
        print(file_path)

        with open(file_path, "r") as file:
            data = yaml.safe_load_all(file)
            for i, doc in enumerate(data):
                # First part of the yaml files is the spec
                if i == 0:
                    continue

                result["pre_opt"]["service_time"].append(
                    doc["pre-optimize"]["service time(us)"]["p50"]
                )
                result["pre_opt"]["tail_latency"].append(
                    doc["pre-optimize"]["tail latency(us)"]["p99"]
                )
                normalized_vcores_pre = round(
                    doc["pre-optimize"]["CPU usage(VCores)"]["vcores"]
                    / doc["pre-optimize"]["CPU usage(VCores)"]["recorded rps"]
                    * 10000,
                    2,
                )
                result["pre_opt"]["cpu_usage"].append(normalized_vcores_pre)

                result["post_opt"]["service_time"].append(
                    doc["post-optimize"]["service time(us)"]["p50"]
                )
                result["post_opt"]["tail_latency"].append(
                    doc["post-optimize"]["tail latency(us)"]["p99"]
                )
                normalized_vcores_post = round(
                    doc["post-optimize"]["CPU usage(VCores)"]["vcores"]
                    / doc["post-optimize"]["CPU usage(VCores)"]["recorded rps"]
                    * 10000,
                    2,
                )
                result["post_opt"]["cpu_usage"].append(normalized_vcores_post)

    print(result)

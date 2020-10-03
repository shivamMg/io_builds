import os
import requests  # noqa We are just importing this to prove the dependency installed correctly
import yaml


def main():
    my_input = os.getenv('INPUT_IO_BUILD_FILE', 'io_builds.yml')

    my_output = "Hello {my_input}".format(my_input=my_input)

    print("::set-output name=myOutput::{my_output}".format(my_output=my_output))
    with open('./io_builds.yml') as f:
        print(yaml.safe_load(f))


if __name__ == "__main__":
    main()

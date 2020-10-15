from collections import namedtuple
import logging
import os
import sys

from rapyuta_io import Client, Build, SimulationOptions, BuildOptions, CatkinOption
from rapyuta_io.utils.utils import get_api_response_data
from rapyuta_io.utils.error import ConflictError
import requests
import yaml

# Environment variables set via 'with'
# https://docs.github.com/en/free-pro-team@latest/actions/reference/workflow-syntax-for-github-actions#jobsjob_idstepswith
INPUT_AUTH_TOKEN = 'INPUT_AUTH_TOKEN'
INPUT_BUILD_POLL_RETRY_COUNT = 'INPUT_BUILD_POLL_RETRY_COUNT'
INPUT_BUILDS_FILE = 'INPUT_BUILDS_FILE'

# Environment variables set by GitHub
# https://docs.github.com/en/free-pro-team@latest/actions/reference/environment-variables#default-environment-variables
GITHUB_REPOSITORY = 'GITHUB_REPOSITORY'
GITHUB_REF = 'GITHUB_REF'

DEFAULT_BUILD_POLL_RETRY_COUNT = 240
DEFAULT_BUILDS_FILE = 'io_builds.yml'

logging.basicConfig(level=logging.INFO, stream=sys.stdout)


def get_builds_with_projects(yaml_data, default_repo):
    builds = []
    try:
        for build in yaml_data['builds']:
            simulation_opts_obj = None
            simulation_opts = build.get('simulationOptions')
            if simulation_opts:
                simulation_opts_obj = SimulationOptions(simulation=simulation_opts['simulation'])

            build_opts_obj = None
            build_opts = build.get('buildOptions')
            if build_opts:
                catkin_opts_obj = []
                for catkin_opt in build_opts['catkinOptions']:
                    catkin_opts_obj.append(CatkinOption(
                        rosPkgs=catkin_opt.get('rosPkgs'),
                        cmakeArgs=catkin_opt.get('cmakeArgs'),
                        makeArgs=catkin_opt.get('makeArgs'),
                        blacklist=catkin_opt.get('blacklist'),
                        catkinMakeArgs=catkin_opt.get('catkinMakeArgs'),
                    ))
                build_opts_obj = BuildOptions(catkinOptions=catkin_opts_obj)

            build_obj = Build(
                buildName=build['buildName'],
                strategyType=build['strategyType'],
                repository=build.get('repository') or default_repo,
                architecture=build['architecture'],
                isRos=build.get('isRos', False),
                rosDistro=build.get('rosDistro', ''),
                contextDir=build.get('contextDir', ''),
                dockerFilePath=build.get('dockerFilePath', ''),
                secret=build.get('secret', ''),
                dockerPullSecret=build.get('dockerPullSecret', ''),
                simulationOptions=simulation_opts_obj,
                buildOptions=build_opts_obj,
            )

            builds.append((build['projectName'], build_obj))
    except KeyError as e:
        logging.error('Invalid {} schema: {} key not found'.format(DEFAULT_BUILDS_FILE, e))
        sys.exit(1)
    except TypeError as e:
        logging.error('Invalid {} schema: {}'.format(DEFAULT_BUILDS_FILE, e))
        sys.exit(1)

    return builds


def get_project_ids(auth_token):
    project_ids = {}
    # TODO: replace with list_projects() method when it's available in sdk
    url = Client('xyz', '')._get_api_endpoints('core_api_host') + '/api/project/list'
    response = requests.get(url, headers={'Authorization': 'Bearer ' + auth_token})
    for project in get_api_response_data(response, parse_full=True):
        project_ids[project['name']] = project['guid']
    return project_ids


def create_or_trigger_build(auth_token, project_id, build):
    cli = Client(auth_token, project_id)
    try:
        build = cli.create_build(build)
    except ConflictError as e:
        logging.info('Build {} already exists: {}'.format(build.buildName, e))
        existing_build = None
        for b in cli.list_builds():
            if build.buildName == b.buildName:
                existing_build = build
        if existing_build.buildInfo.repository != build.buildInfo.repository:
            logging.error('Build {} has repository as {} instead of {}'.format(build.buildName,
                                                                               existing_build.buildInfo.repository,
                                                                               build.buildInfo.repository))
            sys.exit(1)

        logging.info('Triggering existing build: {}'.format(existing_build))
        existing_build.trigger()
        build = existing_build

    return build


def main():
    auth_token = os.getenv(INPUT_AUTH_TOKEN)
    if not auth_token:
        logging.error('{} env not set'.format(INPUT_AUTH_TOKEN))
        sys.exit(1)

    github_repo_path = os.getenv(GITHUB_REPOSITORY)
    if not github_repo_path:
        logging.error('{} env not set'.format(GITHUB_REPOSITORY))
        sys.exit(1)
    github_branch = 'master'
    if os.getenv(GITHUB_REF):
        github_branch = os.getenv(GITHUB_REF)[len('refs/heads/'):]
    default_repo = 'https://github.com/' + github_repo_path + '#' + github_branch

    filepath = os.getenv(INPUT_BUILDS_FILE, DEFAULT_BUILDS_FILE)
    with open(filepath) as f:
        data = yaml.safe_load(f)
    logging.info('Parsed {}: {}'.format(filepath, data))

    builds = get_builds_with_projects(data, default_repo)
    logging.info('Builds: {}'.format(builds))
    project_ids = get_project_ids(auth_token)
    logging.info('Retrieved project ids: {}'.format(project_ids))

    # validate projects before starting builds
    for project_name, _ in builds:
        if not project_ids.get(project_name):
            logging.error('Project {} not available for the given auth token'.format(project_name))
            sys.exit(1)

    started_builds = []
    for project_name, build in builds:
        started_builds.append(
            create_or_trigger_build(auth_token, project_ids[project_name], build),
        )

    for build in started_builds:
        logging.info('Waiting for Build {} to either complete or fail'.format(build.buildName))
        retry_count = os.getenv(INPUT_BUILD_POLL_RETRY_COUNT, DEFAULT_BUILD_POLL_RETRY_COUNT)
        sleep_interval = 5
        logging.info('Polling Build {} with retry_count={} and sleep_interval={}'.format(build.buildName,
                                                                                         retry_count,
                                                                                         sleep_interval))
        build.poll_build_till_ready(retry_count=retry_count, sleep_interval=sleep_interval)
        logging.info('Build {} is complete'.format(build.buildName))


if __name__ == "__main__":
    main()

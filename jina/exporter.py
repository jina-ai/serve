import json
from typing import List

from jina.orchestrate.flow.base import Flow
from jina.orchestrate.deployments import Deployment
from jina.jaml import JAML
from jina.logging.predefined import default_logger
from jina.schemas import get_full_schema
from jina_cli.export import api_to_dict

def export_kubernetes(args):
    """Export to k8s yaml files

    :param args: args from CLI
    """
    from jina.jaml import JAMLCompatible

    try:
        obj = JAMLCompatible.load_config(args.config_path)
    except Exception as e:
        default_logger.error(f"Failed to load config: {e}")
        raise

    if isinstance(obj, (Flow, Deployment)):
        try:
            obj.to_kubernetes_yaml(
                output_base_path=args.outpath, k8s_namespace=args.k8s_namespace
            )
            default_logger.info(f'Kubernetes YAML exported to {args.outpath}')
        except Exception as e:
            default_logger.error(f"Failed to export to Kubernetes YAML: {e}")
            raise
    else:
        raise NotImplementedError(
            f'Object of class {obj.__class__.__name__} cannot be exported to Kubernetes'
        )

def export_docker_compose(args):
    """Export to Docker compose yaml files

    :param args: args from CLI
    """
    from jina.jaml import JAMLCompatible

    try:
        obj = JAMLCompatible.load_config(args.config_path)
    except Exception as e:
        default_logger.error(f"Failed to load config: {e}")
        raise

    if isinstance(obj, (Flow, Deployment)):
        try:
            obj.to_docker_compose_yaml(
                output_path=args.outpath, network_name=args.network_name
            )
            default_logger.info(f'Docker Compose YAML exported to {args.outpath}')
        except Exception as e:
            default_logger.error(f"Failed to export to Docker Compose YAML: {e}")
            raise
    else:
        raise NotImplementedError(
            f'Object of class {obj.__class__.__name__} cannot be exported to Docker Compose'
        )

def export_flowchart(args):
    """Export to flowchart file

    :param args: args from CLI
    """
    try:
        flow = Flow.load_config(args.config_path)
        flow.plot(args.outpath, vertical_layout=args.vertical_layout)
        default_logger.info(f'Flowchart exported to {args.outpath}')
    except Exception as e:
        default_logger.error(f"Failed to export flowchart: {e}")
        raise

def export_schema(args):
    """Export to JSON Schemas

    :param args: args from CLI
    """
    from jina import __version__

    def dump_data(dump_api: dict, paths: List[str], extension: str):
        for path in paths:
            f_name = (path % __version__) if '%s' in path else path
            try:
                with open(f_name, 'w', encoding='utf-8') as fp:
                    if extension == 'yaml':
                        JAML.dump(dump_api, fp)
                    elif extension == 'json':
                        json.dump(dump_api, fp, sort_keys=True)
                    default_logger.info(f'API is exported to {f_name}')
            except Exception as e:
                default_logger.error(f"Failed to export schema to {f_name}: {e}")
                raise

    if args.yaml_path:
        dump_api = api_to_dict()
        dump_data(dump_api, args.yaml_path, 'yaml')

    if args.json_path:
        dump_api = api_to_dict()
        dump_data(dump_api, args.json_path, 'json')

    if args.schema_path:
        dump_api = get_full_schema()
        dump_data(dump_api, args.schema_path, 'json')

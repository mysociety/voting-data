import rich_click as click

from .commons_votes import get_all_months, process_votes


@click.group()
def cli():
    pass


def main():
    cli()


@cli.command()
def load_commons_votes():
    get_all_months()
    process_votes()


if __name__ == "__main__":
    main()

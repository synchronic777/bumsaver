import os
import random
import subprocess
from uuid import uuid4
from datetime import datetime
from os.path import exists
from click import echo
import click
import glob
import json


# Common

def s_print(operation, lvl, message, *args, **kwargs):
    """Standardizes the string format
    :param operation, short string that indicates to the user the step we are going through
    :param lvl, letter that indicates if the displayed message is a Info, Warning or Error
    :param message, the message we want to print
    :param *args, (optional) it's only expected to receive a string representing an uid.
    :return: The user input if input is set to True
    """
    uid = None
    u_input = False
    count = ''
    if len(args) > 0:
        uid = args[0]
    for kwarg, val in kwargs.items():
        if 'cnt' in kwarg and val != '':
            count = f'[{kwargs["cnt"]}]'
        if 'input' in kwarg:
            u_input = True
    string = f"[{(f'{uid}:' if uid else '')}{get_dt()}:{operation}]{count}[{lvl}] {message}"
    if lvl == 'I':
        if not u_input:
            echo(string)
        else:
            return input(string)
    else:
        color = None
        if lvl == 'E':
            color = 'red'
        if lvl == 'W':
            color = 'bright_yellow'
        if not u_input:
            echo(click.style(string, fg=color))
        else:
            return input(click.style(string, fg=color))


def get_dt():
    """
    :return: A timestamp in string format
    """
    return str(datetime.now().strftime('%d%m%y%H%M%S'))


def suid():
    """Generates a short uid
    :return: A unique identifier with a fixed length of 6 characters
    """
    chunks = str(uuid4()).split('-')
    count = 0
    uid = ''
    while count < 3:
        chunk = random.choice(chunks)
        uid = f'{uid}{chunk[:2]}'
        chunks.remove(chunk)
        count += 1
    return uid


# Shlerp script


def update_summ(summ, status):
    if status == 0:
        summ['done'] += 1
    elif status == 1:
        summ['failed'] += 1
    return summ


def iglob_hidden(*args, **kwargs):
    """A glob.iglob that include dot files and hidden files"""
    """The credits goes to the user polyvertex for this function"""
    old_ishidden = glob._ishidden
    glob._ishidden = lambda x: False
    try:
        yield from glob.iglob(*args, **kwargs)
    finally:
        glob._ishidden = old_ishidden


def get_files(path, exclusions, options):
    """Lists the files contained in a given folder, without symlinks
    :param path: String referring to the path that needs it's content to be listed
    :param exclusions: Dictionary containing the files and folders we want to exclude
    :param options: dictionary/object containing exclusion options
    :return: A list of files, without any possible node_modules folder
    """
    if options['nogit']:
        exclusions['folders'].append('.git')
        exclusions['files'].append('.gitignore')
    if options['noexcl']:
        return [
            file for file in os.listdir(path)
            if (exclusions['dep_folder'] and file != exclusions['dep_folder'])
            or not exclusions['dep_folder']
        ]
    elem_list = []
    dep_fld = exclusions['dep_folder']
    for elem in os.listdir(path):
        excl_matched = False
        if (
            not options['keephidden'] and
            elem.startswith('.') and
            not (
                elem == '.git' or
                elem == '.gitignore'
            )
        ):
            excl_matched = True
        if os.path.isdir(f'{path}/{elem}'):
            if exclusions['folders']:
                for fld_excl in exclusions['folders']:
                    if fld_excl in elem:
                        excl_matched = True
                        break
            if dep_fld and dep_fld in elem:
                excl_matched = True
            if not excl_matched:
                elem_list.append(elem)
        else:
            if exclusions['files']:
                for file_excl in exclusions['files']:
                    if file_excl in elem:
                        excl_matched = True
                        break
            if dep_fld and dep_fld in elem:
                excl_matched = True
            if not excl_matched:
                elem_list.append(elem)
    return elem_list


def weight_found(leads):
    """Self-explanatory
    :param leads: List of objects representing potential winners
    :return: True if some patterns has a weight
    """
    for lead in leads:
        if lead['total'] > 0:
            return True
    return False


def elect(leads):
    """Determines which language pattern(s) has the heavier weight
    :param leads: List of objects representing potential winners
    :return: The object(s) that has the heaviest weight
    """
    winner = []
    leads.sort(key=lambda x: x['total'], reverse=True)
    for lead in leads:
        if not winner:
            winner.append(lead)
        else:
            if lead['total'] == winner[0]['total']:
                winner.append(lead)
    return None if len(winner) == 0 else winner


def crawl_for_weight(proj_fld, leads):
    """Crawl the project to find files matching the extensions we provide to this function
    :param proj_fld: text, the folder we want to process
    :param leads: object list containing languages names, extensions to crawl and weights
    :return: an updated list with some more weight (hopefully)
    """
    for lead in leads:
        for ext in lead['extensions']:
            for _ in glob.iglob(f'{proj_fld}/**/{ext["name"]}', recursive=True):
                lead['total'] += ext['weight']
    return leads


def enforce_limit(tmp_file, settings):
    """Shortens the history if it is too long compared to history_limit
    :param tmp_file: Temporary file containing the history list
    :param settings: Param representing
    :return:
    """
    history = tmp_file['rules_history']
    history_limit = settings['rules']['history_limit']
    if len(history) > history_limit:
        history = history[:history_limit]
        with open('tmp.json', 'w') as write_tmp:
            tmp_file['rules_history'] = history
            write_tmp.write(json.dumps(tmp_file, indent=4))


def history_updated(rule, settings, tmp_file):
    """Updates the history with a new rule
    :param rule:  List of objects representing potential winners
    :param settings: The settings of the project
    :param tmp_file:
    :return: A boolean depending on the outcome of this function
    """
    current_lang = rule['name']
    try:
        enforce_limit(tmp_file, settings)
        history = tmp_file['rules_history']
        history_limit = settings['rules']['history_limit']
        # If the current language is in the history
        if current_lang in history:
            # But it's not the latest, get its position and remove it to add it back in first pos
            if history.index(current_lang) != 0:
                current_pos = history.index(current_lang)
                history.pop(current_pos)
                history.insert(0, current_lang)
                with open(f'{os.getcwd()}/tmp.json', 'w') as write_tmp:
                    tmp_file['rules_history'] = history
                    write_tmp.write(json.dumps(tmp_file, indent=4))
                    return True
            return True
        else:
            # If the current language isn't in the list, remove the oldest one if needed and then add it
            if len(history) == history_limit:
                history.pop()
            history.insert(0, current_lang)
            tmp_file['rules_history'] = history
            with open('tmp.json', 'w') as write_tmp:
                write_tmp.write(json.dumps(tmp_file, indent=4))
                return True
    except (FileNotFoundError, ValueError):
        with open(f'{os.getcwd()}/tmp.json', 'a') as write_tmp:
            write_tmp.write(json.dumps({
                "rules_history": [current_lang]
            }))
            if exists(f'{os.getcwd()}/tmp.json'):
                return True
    return False


# Setup script

def req_installed(setup_folder):
    """Attempts to install requirements
    :param setup_folder: str representing the setup folder
    :return: True if it worked, else False
    """
    try:
        venv_bin = f'{setup_folder}venv/bin/'
        pip_path = f'{venv_bin}pip'
        if not exists(pip_path):
            if exists(f'{venv_bin}pip3'):
                pip_path = f'{venv_bin}pip3'
            else:
                return False
        subprocess.check_call([
            pip_path,
            'install', '-r',
            f'{os.getcwd()}/requirements.txt'
        ])
        return True
    except subprocess.CalledProcessError:
        return False

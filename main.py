"""Backup script
Copyright (c) 2023 Mathieu BARBE-GAYET
All Rights Reserved.
Released under the GNU Affero General Public License v3.0
"""
import utils
import os
import shutil
import glob
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo
import time
import click
from click import echo
import json


def auto_detect(proj_fld, settings, uid):
    leads = []
    tried_history = False
    tried_all = False
    while True:
        # Try...Except
        try:
            with open('./rules.json', 'r') as read_file:
                rules = json.load(read_file)
        except FileNotFoundError:
            echo(f'[{uid}:{utils.get_dt()}:scan] ERROR: rules.json not found')
            exit()
        # If the rules history hasn't been checked yet, only keep the rules that are mentioned in the tmp file
        if not tried_history:
            try:
                with open('./tmp.json', 'r') as read_tmp:
                    tmp_file = json.load(read_tmp)
                    rules_history = tmp_file['rules_history']
                    for rule in rules:
                        if rule['name'] not in rules_history:
                            current_pos = rules.index(rule)
                            rules.pop(current_pos)
            except (FileNotFoundError, ValueError):
                echo(f'[{uid}:{utils.get_dt()}:scan] Info: Temp file not found, will use the whole ruleset instead')
                tried_history = True
        else:
            to_prune = []
            for rule_name in rules_history:
                for rule in rules:
                    if rule['name'] == rule_name:
                        to_prune.append(rule)
            for junk in to_prune:
                rules.remove(junk)

        for rule in rules:
            extensions = []
            total = 0
            for file in rule['detect']['files']:
                names = file['name']
                pattern = file['pattern']
                if len(names) == 1:
                    # If only one extension, add it to the extension array
                    if names[0].startswith('*.'):
                        extensions.append({
                            'name': names[0],
                            'weight': file['weight']
                        })
                    else:
                        # If only one filename check if it exists, then check its content
                        filename = names[0]
                        if os.path.exists(f'{proj_fld}/{filename}'):
                            # If the pattern defined in the rule is not set to null, search it in the file
                            if pattern:
                                with open(f'{proj_fld}/{filename}', 'r') as file_content:
                                    if pattern in file_content:
                                        total += file['weight']
                            else:
                                total += file['weight']
                if len(names) > 1:
                    for name in names:
                        if name.startswith('*.'):
                            extensions.append({
                                'name': name,
                                'weight': file['weight']
                            })
                        else:
                            # If the filename is not an extension, check for its existence right away
                            if os.path.exists(f'{proj_fld}/{name}'):
                                total += file['weight']

            for folder in rule['detect']['folders']:
                name = folder['name']
                # We check if each folder from the current rule exists
                if os.path.exists(f'{proj_fld}/{name}/'):
                    # If we don't have any files to check in the folder, increment the rule weight
                    if not folder['files']:
                        total += folder['weight']
                    else:
                        # Make sure that each files from the folder element exists before increasing the weight
                        match = True
                        for file in folder['files']:
                            if not os.path.exists(f'{proj_fld}/{folder["name"]}/{file}'):
                                match = False
                        if match:
                            total += folder['weight']
            leads.append({
                "name": rule['name'],
                "extensions": extensions,
                "total": total
            })

        crawled = False
        if utils.weight_found(leads):
            leads = utils.elect(leads)
        else:
            # If the main method we use to find weight (filename matching) hasn't matched anything
            # Use iglob to match files that have a given extension and update the weights
            leads = utils.crawl_for_weight(proj_fld, leads, uid)
            crawled = True
            if utils.weight_found(leads):
                leads = utils.elect(leads)

        # If weight have been found BUT we have multiple winners, search for more weight
        if utils.weight_found(leads) and len(leads) > 1:
            if not crawled:
                leads = utils.crawl_for_weight(proj_fld, leads, uid)

        if not tried_history:
            tried_history = True
        else:
            tried_all = True

        # Final checks before finishing the current iteration in the loop
        if len(leads) > 1:
            # If we have more than one language remaining it means the autodetection wasn't successful
            leads = list([])
            if tried_all:
                echo(f'[{uid}:{utils.get_dt()}:scan] Warning: Unable to determine the main language for this project')
                break
            else:
                echo(f'[{uid}:{utils.get_dt()}:scan] Info: Trying the whole ruleset...')
                # Ah shit, here we go again
        else:
            if utils.weight_found(leads):
                # Successful exit point
                # Check if the history in the tmp file can be updated before breaking out of the loop
                if not utils.history_updated(leads[0], settings, tmp_file):
                    echo(f'[{uid}:{utils.get_dt()}:scan] Info: A problem occurred when trying to write in tmp.json')
                    break
                else:
                    break
            else:
                leads = list([])
                if tried_all:
                    echo(f'[{uid}:{utils.get_dt()}:scan] Warning: Nothing matched')
                    break
                # Ah shit, here we go again
    return leads[0] if leads else False


def build_archive(project_fld, dst_path, uid, started):
    """Makes an archive of a given folder, without node_modules
    :param project_fld: text, the folder we want to archive
    :param dst_path: text, the location where we want to store the archive
    :param uid: text representing a short uid
    :param started: number representing the time when the script has been executed
    """
    with ZipFile(f'{dst_path}.zip', 'w', ZIP_DEFLATED, compresslevel=9) as zip_archive:
        fld_count = file_count = symlink_count = 0
        success = False
        for filename in glob.iglob(project_fld + '/**', recursive=True):
            if 'node_modules' not in filename:
                rel_filename = filename.split(f'{project_fld}/')[1]
                # Exclude '' (listed by iglob when the script is executed from another path in a terminal)
                if rel_filename != '':
                    # If the filename is actually a symbolic link, use zip_info and zipfile.writestr()
                    # Source: https://gist.github.com/kgn/610907
                    if os.path.islink(filename):
                        symlink_count += 1
                        # http://www.mail-archive.com/python-list@python.org/msg34223.html
                        zip_info = ZipInfo(filename)
                        zip_info.create_system = 3
                        # long type of hex val of '0xA1ED0000L',
                        # say, symlink attr magic...
                        zip_info.external_attr = 2716663808
                        try:
                            zip_archive.writestr(zip_info, os.readlink(f'{filename}'))
                            echo(f'[{uid}:{utils.get_dt()}:arch] Done: {rel_filename}')
                            success = True
                        except Exception as exc:
                            echo(f'[{uid}:{utils.get_dt()}:arch]'
                                 f'A problem happened while handling {rel_filename}: {exc}')

                    else:
                        try:
                            zip_archive.write(f'{filename}', arcname=f'{rel_filename}')
                            if os.path.isdir(filename):
                                fld_count += 1
                            else:
                                file_count += 1
                            echo(f'[{uid}:{utils.get_dt()}:arch] Done: {rel_filename}')
                            success = True
                        except Exception as exc:
                            echo(
                                f'[{uid}:{utils.get_dt()}:arch] '
                                f'A problem happened while handling {rel_filename}: {exc}')
        if success:
            echo('------------')
            echo(f'[{uid}:{utils.get_dt()}:arch] '
                 f'Folders: {fld_count} - '
                 f'Files: {file_count} - '
                 f'Symbolic links: {symlink_count}')
            echo(
                f'[{uid}:{utils.get_dt()}:arch] '
                f'✅ Project archived ({"%.2f" % (time.time() - started)}s): {dst_path}.zip')
        else:
            echo(f'[{uid}:{utils.get_dt()}:arch] Warning - Corrupted archive: {dst_path}.zip')


# def duplicate(path, dst, cache, uid, started):
def duplicate(path, dst, uid, started):
    """Duplicates a project folder, processes all files and folders. node_modules will be processed last if cache = True
    :param path, string that represents the project folder we want to duplicate
    :param dst, string that represents the destination folder where we will copy the project files
    :param uid, text representing a short uid
    :param started: number representing the time when the script has been executed
    """
    try:
        fld_count = file_count = symlink_count = 0
        elem_list = utils.get_files(path)
        os.mkdir(dst)
        for elem in elem_list:
            orig = f'{path}/{elem}'
            full_dst = f'{dst}/{elem}'
            if os.path.isdir(orig):
                shutil.copytree(orig, full_dst, symlinks=True)
                if utils.exists(full_dst):
                    echo(f'[{uid}:{utils.get_dt()}:copy] Done: {path}/{elem}')
                    fld_count += 1
            else:
                shutil.copy(orig, full_dst)
                if os.path.islink(elem):
                    symlink_count += 1
                else:
                    file_count += 1
                if utils.exists(full_dst):
                    echo(f'[{uid}:{utils.get_dt()}:copy] Done: {path}/{elem}')
        echo('------------')
        # echo(f'[{uid}:{utils.get_dt()}:arch] '
        #       f'Folders: {fld_count} - '
        #       f'Files: {file_count} - '
        #       f'Symbolic links: {symlink_count}')
        echo(f'[{uid}:{utils.get_dt()}:copy] ✅ Project duplicated ({"%.2f" % (time.time() - started)}s): {dst}/')
        # if cache:
        #     start_cache = time.time()
        #     echo(f'[{uid}:{utils.get_dt()}:copy] Processing node_modules...')
        #     shutil.copytree(f'{path}/node_modules', f'{dst}/node_modules', symlinks=True)
        #     echo(f'[{uid}:{utils.get_dt()}:copy] Done ({"%.2f" % (time.time() - start_cache)}s): {dst}/node_modules/')
    except Exception as exc:
        echo(f'[{uid}:{utils.get_dt()}:copy] Error during the duplication', exc)


@click.command()
@click.option('-p', '--path', type=click.Path(),
              help='The path of the project we want to backup. Please use absolute paths for now')
@click.option('-o', '--output', type=click.Path(),
              help='The location where we want to store the backup')
@click.option('-r', '--rule', default=False,
              help='Manually specify a rule name if you want')
# @click.option('-c', '--cache', default=False,
#               help='Includes node_modules in the duplication. Only works in conjunction with -a',
#               is_flag=True)
# @click.option('-ai', '--autoinstall', default=False,
#               help='Installs the node modules. Don\'t use it with -c.',
#               is_flag=True)
@click.option('-a', '--archive', default=False,
              help='Archives the project folder instead of making a copy of it',
              is_flag=True)
def main(path, output, rule, archive):
    """Dev projects backups made easy"""
    start_time = time.time()
    if path:
        proj_fld = os.path.abspath(path)
    else:
        proj_fld = os.getcwd()
    with open('./settings.json', 'r') as read_settings:
        settings = json.load(read_settings)

    uid = utils.suid()
    if not rule:
        rule_detected = auto_detect(proj_fld, settings, uid)
        if rule_detected:
            rule = rule_detected
            echo(f'[{uid}:{utils.get_dt()}:scan] Info: Matching rule: {rule["name"]}')
        else:
            echo(f'[{uid}:{utils.get_dt()}:scan] Error: Please select a rule to apply with --rule')
            exit()
    # TODO: Apply the actions (begin with exclusions)

    # # If we don't have a particular output folder, use the same as the project
    # if output:
    #     output = os.path.abspath(output)
    #     project_name = proj_fld.split('/')[-1]
    #     dst = f'{output}/{project_name}_{utils.get_dt()}'
    # else:
    #     dst = f'{proj_fld}_{utils.get_dt()}'
    # if archive:
    #     # If the -a switch is provided to the script, we use build_archive() and exclude the node_module folder
    #     build_archive(proj_fld, dst, uid, start_time)
    # else:
    #     # Else if we don't want an archive we will do a copy of the project instead
    #     if not cache:
    #         # Copy everything except the node_modules folder
    #         duplicate(proj_fld, dst, False, uid, start_time)
    #         # if autoinstall:
    #         #     echo('Installing npm packages...')
    #         #     os.system('npm i')
    #     else:
    #         if node_modules:
    #             duplicate(proj_fld, dst, True, uid, start_time)
    #         else:
    #             duplicate(proj_fld, dst, False, uid, start_time)



if __name__ == '__main__':
    main()

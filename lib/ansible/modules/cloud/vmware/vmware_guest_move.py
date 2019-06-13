#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2018, Jose Angel Munoz <josea.munoz () gmail.com>
# Copyright: (c) 2018, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = r'''
---
module: vmware_guest_move
short_description: Moves virtual machines in vCenter
description:
    - This module can be used to move virtual machines between folders.
version_added: '2.7'
author:
    - Jose Angel Munoz (@imjoseangel)
notes:
    - Tested on vSphere 5.5 and vSphere 6.5
requirements:
    - python >= 2.6
    - PyVmomi
options:
   name:
        description:
            - Name of the existing virtual machine to move.
            - This is required if C(UUID) is not supplied.
   uuid:
        description:
            - UUID of the virtual machine to manage if known, this is VMware's unique identifier.
            - This is required if C(name) is not supplied.
   use_instance_uuid:
        description:
            - Whether to use the VMWare instance UUID rather than the BIOS UUID.
        default: no
        type: bool
        version_added: '2.8'
   name_match:
        description:
            - If multiple virtual machines matching the name, use the first or last found.
        default: 'first'
        choices: [ first, last ]
   dest_folder:
        description:
            - Absolute path to move an existing guest
            - The dest_folder should include the datacenter. ESX's datacenter is ha-datacenter.
            - This parameter is case sensitive.
            - 'Examples:'
            - '   dest_folder: /ha-datacenter/vm'
            - '   dest_folder: ha-datacenter/vm'
            - '   dest_folder: /datacenter1/vm'
            - '   dest_folder: datacenter1/vm'
            - '   dest_folder: /datacenter1/vm/folder1'
            - '   dest_folder: datacenter1/vm/folder1'
            - '   dest_folder: /folder1/datacenter1/vm'
            - '   dest_folder: folder1/datacenter1/vm'
            - '   dest_folder: /folder1/datacenter1/vm/folder2'
        required: True
   datacenter:
        description:
            - Destination datacenter for the move operation
        required: True
extends_documentation_fragment: vmware.documentation
'''

EXAMPLES = r'''
- name: Move Virtual Machine
  vmware_guest_move:
    hostname: "{{ vcenter_hostname }}"
    username: "{{ vcenter_username }}"
    password: "{{ vcenter_password }}"
    datacenter: datacenter
    validate_certs: no
    name: testvm-1
    dest_folder: "/{{ datacenter }}/vm"
  delegate_to: localhost

- name: Get VM UUID
  vmware_guest_facts:
    hostname: "{{ vcenter_hostname }}"
    username: "{{ vcenter_username }}"
    password: "{{ vcenter_password }}"
    validate_certs: no
    datacenter: "{{ datacenter }}"
    folder: "/{{datacenter}}/vm"
    name: "{{ vm_name }}"
  delegate_to: localhost
  register: vm_facts

- name: Get UUID from previous task and pass it to this task
  vmware_guest_move:
    hostname: "{{ vcenter_hostname }}"
    username: "{{ vcenter_username }}"
    password: "{{ vcenter_password }}"
    validate_certs: no
    datacenter: "{{ datacenter }}"
    uuid: "{{ vm_facts.instance.hw_product_uuid }}"
    dest_folder: "/DataCenter/vm/path/to/new/folder/where/we/want"
  delegate_to: localhost
  register: facts
'''

RETURN = """
instance:
    description: metadata about the virtual machine
    returned: always
    type: dict
    sample: {
        "annotation": null,
        "current_snapshot": null,
        "customvalues": {},
        "guest_consolidation_needed": false,
        "guest_question": null,
        "guest_tools_status": null,
        "guest_tools_version": "0",
        "hw_cores_per_socket": 1,
        "hw_datastores": [
            "LocalDS_0"
        ],
        "hw_esxi_host": "DC0_H0",
        "hw_eth0": {
            "addresstype": "generated",
            "ipaddresses": null,
            "label": "ethernet-0",
            "macaddress": "00:0c:29:6b:34:2c",
            "macaddress_dash": "00-0c-29-6b-34-2c",
            "summary": "DVSwitch: 43cdd1db-1ef7-4016-9bbe-d96395616199"
        },
        "hw_files": [
            "[LocalDS_0] DC0_H0_VM0/DC0_H0_VM0.vmx"
        ],
        "hw_folder": "/F0/DC0/vm/F0",
        "hw_guest_full_name": null,
        "hw_guest_ha_state": null,
        "hw_guest_id": "otherGuest",
        "hw_interfaces": [
            "eth0"
        ],
        "hw_is_template": false,
        "hw_memtotal_mb": 32,
        "hw_name": "DC0_H0_VM0",
        "hw_power_status": "poweredOn",
        "hw_processor_count": 1,
        "hw_product_uuid": "581c2808-64fb-45ee-871f-6a745525cb29",
        "instance_uuid": "8bcb0b6e-3a7d-4513-bf6a-051d15344352",
        "ipv4": null,
        "ipv6": null,
        "module_hw": true,
        "snapshots": []
    }
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_native
from ansible.module_utils.vmware import PyVmomi, vmware_argument_spec, wait_for_task


class PyVmomiHelper(PyVmomi):
    def __init__(self, module):
        super(PyVmomiHelper, self).__init__(module)


def main():
    argument_spec = vmware_argument_spec()
    argument_spec.update(
        name=dict(type='str'),
        name_match=dict(
            type='str', choices=['first', 'last'], default='first'),
        uuid=dict(type='str'),
        use_instance_uuid=dict(type='bool', default=False),
        dest_folder=dict(type='str', required=True),
        datacenter=dict(type='str', required=True),
    )
    module = AnsibleModule(
        argument_spec=argument_spec,
        required_one_of=[
            ['name', 'uuid']
        ],
        mutually_exclusive=[
            ['name', 'uuid']
        ],
        supports_check_mode=True
    )

    # FindByInventoryPath() does not require an absolute path
    # so we should leave the input folder path unmodified
    module.params['dest_folder'] = module.params['dest_folder'].rstrip('/')
    pyv = PyVmomiHelper(module)
    search_index = pyv.content.searchIndex

    # Check if the VM exists before continuing
    vm = pyv.get_vm()

    # VM exists
    if vm:
        try:
            vm_path = pyv.get_vm_path(pyv.content, vm).lstrip('/')
            if module.params['name']:
                vm_name = module.params['name']
            else:
                vm_name = vm.name

            vm_full = vm_path + '/' + vm_name
            folder = search_index.FindByInventoryPath(module.params['dest_folder'])
            if folder is None:
                module.fail_json(msg="Folder name and/or path does not exist")
            vm_to_move = search_index.FindByInventoryPath(vm_full)
            if module.check_mode:
                module.exit_json(changed=True, instance=pyv.gather_facts(vm))
            if vm_path != module.params['dest_folder'].lstrip('/'):
                move_task = folder.MoveInto([vm_to_move])
                changed, err = wait_for_task(move_task)
                if changed:
                    module.exit_json(
                        changed=True, instance=pyv.gather_facts(vm))
            else:
                module.exit_json(instance=pyv.gather_facts(vm))
        except Exception as exc:
            module.fail_json(msg="Failed to move VM with exception %s" %
                             to_native(exc))
    else:
        if module.check_mode:
            module.exit_json(changed=False)
        module.fail_json(msg="Unable to find VM %s to move to %s" % (
            (module.params.get('uuid') or module.params.get('name')),
            module.params.get('dest_folder')))


if __name__ == '__main__':
    main()

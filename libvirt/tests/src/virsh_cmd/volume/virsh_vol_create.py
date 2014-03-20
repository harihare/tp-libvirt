import os
import logging
from virttest import virsh, libvirt_storage, libvirt_xml
from virttest.utils_test import libvirt as utlv
from autotest.client.shared import error


def run(test, params, env):
    """
    Test virsh vol-create command to cover the following matrix:
    pool_type = [dir, fs, netfs]
    volume_format = [raw, bochs, cloop, cow, dmg, iso, qcow, qcow2, qed,
                     vmdk, vpc]

    pool_type = [disk]
    volume_format = [none, linux, fat16, fat32, linux-swap, linux-lvm,
                     linux-raid, extended]

    pool_type = [logical]
    volume_format = [none]

    pool_type = [iscsi, scsi]
    Not supported with format type

    TODO:
    pool_type = [rbd, glusterfs]

    Reference: http://www.libvirt.org/storage.html
    """

    src_pool_type = params.get("src_pool_type")
    src_pool_target = params.get("src_pool_target")
    src_emulated_image = params.get("src_emulated_image")
    extra_option = params.get("extra_option", "")
    vol_name = params.get("vol_name", "vol_create_test")
    vol_format = params.get("vol_format")
    lazy_refcounts = "yes" == params.get("lazy_refcounts")
    status_error = "yes" == params.get("status_error", "no")

    # Set volume xml attribute dictionary, extract all params start with 'vol_'
    # which are for setting volume xml, except 'lazy_refcounts'.
    vol_arg = {}
    for key in params.keys():
        if key.startswith('vol_'):
            if key[4:] in ['capacity', 'allocation', 'owner', 'group']:
                vol_arg[key[4:]] = int(params[key])
            else:
                vol_arg[key[4:]] = params[key]
    vol_arg['lazy_refcounts'] = lazy_refcounts

    pool_type = ['dir', 'disk', 'fs', 'logical', 'netfs', 'iscsi', 'scsi']
    if src_pool_type not in pool_type:
        raise error.TestNAError("pool type %s not in supported type list: %s" %
                                (src_pool_type, pool_type))

    try:
        # Create the src pool
        src_pool_name = "virt-%s-pool" % src_pool_type
        pvt = utlv.PoolVolumeTest(test, params)
        pvt.pre_pool(src_pool_name, src_pool_type, src_pool_target,
                     src_emulated_image, image_size="2G",
                     pre_disk_vol=["1M"])

        # Print current pools for debugging
        logging.debug("Current pools:%s",
                      libvirt_storage.StoragePool().list_pools())

        # Set volume xml file
        volxml = libvirt_xml.VolXML()
        newvol = volxml.new_vol(**vol_arg)
        vol_xml = newvol['xml']

        # Run virsh_vol_create to create vol
        logging.debug("create volume from xml: %s" % newvol.xmltreefile)
        cmd_result = virsh.vol_create(src_pool_name, vol_xml, extra_option,
                                      ignore_status=True, debug=True)
        status = cmd_result.exit_status
        # Check result
        if not status_error:
            if not status:
                src_pv = libvirt_storage.PoolVolume(src_pool_name)
                src_volumes = src_pv.list_volumes().keys()
                logging.debug("Current volumes in %s: %s",
                              src_pool_name, src_volumes)
                if vol_name not in src_volumes:
                    raise error.TestFail("Can't find volume: %s from pool: %s"
                                         % (vol_name, src_pool_name))
                # check format in volume xml
                post_xml = volxml.new_from_vol_dumpxml(vol_name, src_pool_name)
                logging.debug("the created volume xml is: %s" %
                              post_xml.xmltreefile)
                if 'format' in post_xml.keys():
                    if post_xml.format != vol_format:
                        raise error.TestFail("Volume format %s is not expected"
                                             % vol_format + " as defined.")
            else:
                # Skip the format not supported by qemu-img error
                if vol_format:
                    fmt_err = "qemu-img: Unknown file format '%s'" % vol_format
                    fmt_err1 = "qemu-img: Formatting or formatting option " +\
                               "not supported for file format '%s'" % vol_format
                    if fmt_err in cmd_result.stderr or \
                       fmt_err1 in cmd_result.stderr:
                        raise error.TestNAError("Volume format %s is not " %
                                                vol_format + "supported.")
                    else:
                        raise error.TestFail("Run failed with right command.")
                else:
                    raise error.TestFail("Run failed with right command.")
        else:
            if status:
                logging.debug("Expect error: %s", cmd_result.stderr)
            else:
                raise error.TestFail("Expect fail, but run successfully!")
    finally:
        # Cleanup
        try:
            pvt.cleanup_pool(src_pool_name, src_pool_type, src_pool_target,
                             src_emulated_image)
        except error.TestFail, detail:
            logging.error(str(detail))

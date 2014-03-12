# Written by Niels Zeilemaker

# see LICENSE.txt for license information
import wx
import wx.lib.imagebrowser as ib
import sys
import os
import tempfile
import atexit
import time
import logging

from Tribler.Core.simpledefs import UPLOAD, DOWNLOAD, \
    STATEDIR_TORRENTCOLL_DIR, STATEDIR_SWIFTRESEED_DIR
from Tribler.Core.Session import Session
from Tribler.Core.SessionConfig import SessionStartupConfig
from Tribler.Core.osutils import get_picture_dir
from Tribler.Core.Utilities.utilities import isInteger

from Tribler.Main.globals import DefaultDownloadStartupConfig, get_default_dscfg_filename
from Tribler.Main.vwxGUI.GuiUtility import GUIUtility
from Tribler.Main.vwxGUI.GuiImageManager import GuiImageManager, data2wxBitmap, ICON_MAX_DIM
from Tribler.Main.vwxGUI.widgets import _set_font


def create_section(parent, hsizer, label):
    panel = wx.Panel(parent)

    vsizer = wx.BoxSizer(wx.VERTICAL)

    title = wx.StaticText(panel, label=label)
    _set_font(title, 1, wx.FONTWEIGHT_BOLD)
    vsizer.Add(title, 0, wx.EXPAND | wx.BOTTOM, 7)

    hsizer.Add(panel, 1, wx.EXPAND)
    panel.SetSizer(vsizer)
    return panel, vsizer

def create_subsection(parent, parent_sizer, label, num_cols=1, vgap=0, hgap=0):
    line = wx.StaticLine(parent, size=(-1,1), style=wx.LI_HORIZONTAL)
    parent_sizer.Add(line, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 7)

    title = wx.StaticText(parent, label=label)
    _set_font(title, 0, wx.FONTWEIGHT_BOLD)
    parent_sizer.Add(title, 0, wx.EXPAND)

    if num_cols == 1:
        sizer = wx.BoxSizer(wx.VERTICAL)
    else:
        sizer = wx.FlexGridSizer(cols=num_cols, vgap=vgap, hgap=hgap)
        sizer.AddGrowableCol(1)

    parent_sizer.Add(sizer, 0, wx.EXPAND)
    return sizer


class SettingsDialog(wx.Dialog):

    def __init__(self):
        super(SettingsDialog, self).__init__(None, size=(600, 600),
            title="Settings", name="settingsDialog")
        self._logger = logging.getLogger(self.__class__.__name__)

        self.ELEMENT_NAME_LIST = ['myNameField',
                             'thumb',
                             'edit',
                             'browse',
                             'firewallValue',
                             'firewallStatusText',
                             'uploadCtrl',
                             'downloadCtrl',
                             'diskLocationCtrl',
                             'diskLocationChoice',
                             'portChange',
                             'minimize_to_tray',
                             't4t0', 't4t0choice', 't4t1', 't4t2', 't4t2text', 't4t3',
                             'g2g0', 'g2g0choice', 'g2g1', 'g2g2', 'g2g2text', 'g2g3',
                             'use_webui',
                             'webui_port',
                             'lt_proxytype',
                             'lt_proxyserver',
                             'lt_proxyport',
                             'lt_proxyusername',
                             'lt_proxypassword',
                             'enable_utp']

        self.myname = None
        self.elements = {}
        self.currentPortValue = None

        self.__init_dialog()

    def __create_dialog(self):
        self._tree_ctrl = wx.TreeCtrl(self, name="settings_tree",
            style=wx.TR_DEFAULT_STYLE | wx.SUNKEN_BORDER | wx.TR_HIDE_ROOT | wx.TR_SINGLE)
        self._tree_ctrl.SetMinSize(wx.Size(150, -1))
        tree_root = self._tree_ctrl.AddRoot('Root')
        self._tree_ctrl.Bind(wx.EVT_TREE_SEL_CHANGING, self.OnSelectionChanging)

        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        hsizer.Add(self._tree_ctrl, 0, wx.EXPAND | wx.RIGHT, 10)

        self._general_panel, self._general_id = self.__create_s1(tree_root, hsizer)
        self._conn_panel, self._conn_id = self.__create_s2(tree_root, hsizer)
        self._bandwidth_panel, self._bandwidth_id = self.__create_s3(tree_root, hsizer)
        self._seeding_panel, self._seeding_id = self.__create_s4(tree_root, hsizer)
        self._experimental_panel, self._experimental_id = self.__create_s5(tree_root, hsizer)

        self._general_panel.Show(True)
        self._conn_panel.Show(False)
        self._bandwidth_panel.Show(False)
        self._seeding_panel.Show(False)
        self._experimental_panel.Show(False)

        self._save_btn = wx.Button(self, wx.ID_OK, label="Save")
        self._cancel_btn = wx.Button(self, wx.ID_CANCEL, label="Cancel")

        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(self._save_btn)
        btn_sizer.AddButton(self._cancel_btn)
        btn_sizer.Realize()

        vsizer = wx.BoxSizer(wx.VERTICAL)
        vsizer.Add(hsizer, 1, wx.EXPAND)
        vsizer.Add(btn_sizer, 0, wx.EXPAND)
        self.SetSizer(vsizer)

    def __init_dialog(self):
        self.guiUtility = GUIUtility.getInstance()
        self.utility = self.guiUtility.utility
        self.defaultDLConfig = DefaultDownloadStartupConfig.getInstance()

        self.__create_dialog()

        for element_name in self.ELEMENT_NAME_LIST:
            element = self.FindWindowByName(element_name)
            if not element:
                self._logger.info('settingsOverviewPanel: Error: Could not identify xrc element: %s', element_name)
            self.elements[element_name] = element

        self._tree_ctrl.Bind(wx.EVT_TREE_SEL_CHANGING, self.OnSelectionChanging)

        # Bind event listeners
        self.elements['uploadCtrl'].Bind(wx.EVT_KEY_DOWN, self.removeUnlimited)
        self.elements['downloadCtrl'].Bind(wx.EVT_KEY_DOWN, self.removeUnlimited)

        self.elements['edit'].Bind(wx.EVT_BUTTON, self.EditClicked)
        self.elements['browse'].Bind(wx.EVT_BUTTON, self.BrowseClicked)

        self.elements['lt_proxytype'].Bind(wx.EVT_CHOICE, self.ProxyTypeChanged)

        self._save_btn.Bind(wx.EVT_BUTTON, self.saveAll)
        self._cancel_btn.Bind(wx.EVT_BUTTON, self.cancelAll)

        # Loading settings
        self.myname = self.utility.session.get_nickname()
        mime, data = self.utility.session.get_mugshot()
        if data is None:
            gui_image_manager = GuiImageManager.getInstance()
            self.mugshot = gui_image_manager.getImage(u"PEER_THUMB")
        else:
            self.mugshot = data2wxBitmap(mime, data)

        self.elements['myNameField'].SetValue(self.myname)
        self.elements['thumb'].SetBitmap(self.mugshot)

        if self.guiUtility.frame.SRstatusbar.IsReachable():
            self.elements['firewallStatusText'].SetLabel('Your network connection is working properly.')
        else:
            self.elements['firewallStatusText'].SetLabel('Tribler has not yet received any incoming connections. \nUnless you\'re using a proxy, this could indicate a problem\nwith your network connection.')

        self.currentPortValue = str(self.utility.session.get_listen_port())
        self.elements['firewallValue'].SetValue(self.currentPortValue)

        convert = lambda v: 'unlimited' if v == 0 else ('0' if v == -1 else str(v))
        self.elements['downloadCtrl'].SetValue(convert(self.utility.read_config('maxdownloadrate')))
        self.elements['uploadCtrl'].SetValue(convert(self.utility.read_config('maxuploadrate')))

        self.currentDestDir = self.defaultDLConfig.get_dest_dir()
        self.elements['diskLocationCtrl'].SetValue(self.currentDestDir)
        self.elements['diskLocationChoice'].SetValue(self.utility.read_config('showsaveas'))

        if sys.platform != "darwin":
            min_to_tray = self.utility.read_config('mintray') == 1
            self.elements['minimize_to_tray'].SetValue(min_to_tray)
        else:
            self.elements['minimize_to_tray'].Enable(False)

        self.elements['t4t0'].SetLabel(self.utility.lang.get('no_leeching'))
        self.elements['t4t0'].Refresh()
        self.elements['t4t1'].SetLabel(self.utility.lang.get('unlimited_seeding'))
        self.elements['t4t2'].SetLabel(self.utility.lang.get('seed_sometime'))
        self.elements['t4t3'].SetLabel(self.utility.lang.get('no_seeding'))

        self.elements['g2g0'].SetLabel(self.utility.lang.get('seed_for_large_ratio'))
        self.elements['g2g1'].SetLabel(self.utility.lang.get('boost__reputation'))
        self.elements['g2g2'].SetLabel(self.utility.lang.get('seed_sometime'))
        self.elements['g2g3'].SetLabel(self.utility.lang.get('no_seeding'))

        t4t_option = self.utility.read_config('t4t_option')
        self.elements['t4t%d' % t4t_option].SetValue(True)
        t4t_ratio = self.utility.read_config('t4t_ratio') / 100.0
        index = self.elements['t4t0choice'].FindString(str(t4t_ratio))
        if index != wx.NOT_FOUND:
            self.elements['t4t0choice'].Select(index)

        t4t_hours = self.utility.read_config('t4t_hours')
        t4t_minutes = self.utility.read_config('t4t_mins')
        self.elements['t4t2text'].SetLabel("%d:%d" % (t4t_hours, t4t_minutes))

        g2g_option = self.utility.read_config('g2g_option')
        self.elements['g2g%d' % g2g_option].SetValue(True)
        g2g_ratio = self.utility.read_config('g2g_ratio') / 100.0
        index = self.elements['g2g0choice'].FindString(str(g2g_ratio))
        if index != wx.NOT_FOUND:
            self.elements['g2g0choice'].Select(index)

        g2g_hours = self.utility.read_config('g2g_hours')
        g2g_mins = self.utility.read_config('g2g_mins')
        self.elements['g2g2text'].SetLabel("%d:%d" % (g2g_hours, g2g_mins))

        self.elements['use_webui'].SetValue(self.utility.read_config('use_webui'))
        self.elements['webui_port'].SetValue(str(self.utility.read_config('webui_port')))

        ptype, server, auth = self.utility.session.get_libtorrent_proxy_settings()
        self.elements['lt_proxytype'].SetSelection(ptype)
        if server:
            self.elements['lt_proxyserver'].SetValue(server[0])
            self.elements['lt_proxyport'].SetValue(str(server[1]))
        if auth:
            self.elements['lt_proxyusername'].SetValue(auth[0])
            self.elements['lt_proxypassword'].SetValue(auth[1])
        self.ProxyTypeChanged()

        self.elements['enable_utp'].SetValue(self.utility.session.get_libtorrent_utp())

        self._tree_ctrl.SelectItem(self._general_id)

        wx.CallAfter(self.Refresh)

    def OnSelectionChanging(self, event):
        old_item = event.GetOldItem()
        new_item = event.GetItem()
        try:
            self.ShowPage(self._tree_ctrl.GetItemData(new_item).GetData(), self._tree_ctrl.GetItemData(old_item).GetData())
        except:
            pass

    def ShowPage(self, page, oldpage):
        if oldpage == None:
            selection = self._tree_ctrl.GetSelection()
            oldpage = self._tree_ctrl.GetItemData(selection).GetData()

        oldpage.Hide()

        page.Show(True)
        page.Layout()

        self.Layout()
        self.Refresh()

    def setUp(self, value, event=None):
        self.resetUploadDownloadCtrlColour()
        self.elements['uploadCtrl'].SetValue(str(value))

        if event:
            event.Skip()

    def setDown(self, value, event=None):
        self.resetUploadDownloadCtrlColour()
        self.elements['downloadCtrl'].SetValue(str(value))

        if event:
            event.Skip()

    def resetUploadDownloadCtrlColour(self):
        self.elements['uploadCtrl'].SetForegroundColour(wx.BLACK)
        self.elements['downloadCtrl'].SetForegroundColour(wx.BLACK)

    def removeUnlimited(self, event):
        textCtrl = event.GetEventObject()
        if textCtrl.GetValue().strip() == 'unlimited':
            textCtrl.SetValue('')
        event.Skip()

    def saveAll(self, event):
        errors = {}

        valdown = self.elements['downloadCtrl'].GetValue().strip()
        if valdown != 'unlimited' and (not valdown.isdigit() or int(valdown) <= 0):
            errors['downloadCtrl'] = 'Value must be a digit'

        valup = self.elements['uploadCtrl'].GetValue().strip()
        if valup != 'unlimited' and (not valup.isdigit() or int(valup) < 0):
            errors['uploadCtrl'] = 'Value must be a digit'

        valport = self.elements['firewallValue'].GetValue().strip()
        if not isInteger(valport):
            errors['firewallValue'] = 'Value must be a digit'

        valdir = self.elements['diskLocationCtrl'].GetValue().strip()
        if not os.path.exists(valdir):
            errors['diskLocationCtrl'] = 'Location does not exist'

        valname = self.elements['myNameField'].GetValue()
        if len(valname) > 40:
            errors['myNameField'] = 'Max 40 characters'

        hours_min = self.elements['t4t2text'].GetValue()
        if len(hours_min) == 0:
            if self.elements['t4t2'].GetValue():
                errors['t4t2text'] = 'Need value'
        else:
            hours_min = hours_min.split(':')

            for value in hours_min:
                if not value.isdigit():
                    if self.elements['t4t2'].GetValue():
                        errors['t4t2text'] = 'Needs to be integer'
                    else:
                        self.elements['t4t2text'].SetValue('')

        hours_min = self.elements['g2g2text'].GetValue()
        if len(hours_min) == 0:
            if self.elements['g2g2'].GetValue():
                errors['g2g2text'] = 'Need value'
        else:
            hours_min = hours_min.split(':')
            for value in hours_min:
                if not value.isdigit():
                    if self.elements['g2g2'].GetValue():
                        errors['g2g2text'] = 'Needs to be hours:minutes'
                    else:
                        self.elements['g2g2text'].SetValue('')

        valwebuiport = self.elements['webui_port'].GetValue().strip()
        if not isInteger(valwebuiport):
            errors['webui_port'] = 'Value must be a digit'

        valltproxyport = self.elements['lt_proxyport'].GetValue().strip()
        if not valltproxyport.isdigit() and (self.elements['lt_proxytype'].GetSelection() or valltproxyport != ''):
            errors['lt_proxyport'] = 'Value must be a digit'

        if len(errors) == 0:  # No errors found, continue saving
            restart = False

            state_dir = self.utility.session.get_state_dir()
            cfgfilename = self.utility.session.get_default_config_filename(state_dir)
            scfg = SessionStartupConfig.load(cfgfilename)

            convert = lambda v: 0 if v == 'unlimited' else (-1 if v == '0' else int(v))
            for config_option, value in [('maxdownloadrate', convert(valdown)), ('maxuploadrate', convert(valup))]:
                if self.utility.read_config(config_option) != value:
                    self.utility.write_config(config_option, value)
                    self.guiUtility.app.ratelimiter.set_global_max_speed(UPLOAD if config_option == 'maxuploadrate' else DOWNLOAD, value)

            if valport != self.currentPortValue:
                scfg.set_listen_port(int(valport))

                scfg.set_dispersy_port(int(valport) - 1)
                self.saveDefaultDownloadConfig(scfg)

                self.guiUtility.set_firewall_restart(True)
                restart = True

            showSave = int(self.elements['diskLocationChoice'].IsChecked())
            if showSave != self.utility.read_config('showsaveas'):
                self.utility.write_config('showsaveas', showSave)
                self.saveDefaultDownloadConfig(scfg)

            if valdir != self.currentDestDir:
                self.defaultDLConfig.set_dest_dir(valdir)

                self.saveDefaultDownloadConfig(scfg)
                self.moveCollectedTorrents(self.currentDestDir, valdir)
                restart = True

            useWebUI = self.elements['use_webui'].IsChecked()
            if useWebUI != self.utility.read_config('use_webui'):
                self.utility.write_config('use_webui', useWebUI)
                restart = True

            if valwebuiport != str(self.utility.read_config('webui_port')):
                self.utility.write_config('webui_port', valwebuiport)
                restart = True

            curMintray = self.utility.read_config('mintray')
            minimizeToTray = 1 if self.elements['minimize_to_tray'].IsChecked() else 0
            if minimizeToTray != curMintray:
                self.utility.write_config('mintray', minimizeToTray)

            for target in [scfg, self.utility.session]:
                try:
                    target.set_nickname(self.elements['myNameField'].GetValue())
                    if getattr(self, 'icondata', False):
                        target.set_mugshot(self.icondata, mime='image/jpeg')
                except:
                    self._logger.exception("Could not set target")

            # tit-4-tat
            t4t_option = self.utility.read_config('t4t_option')
            for i in range(4):
                if self.elements['t4t%d' % i].GetValue():
                    self.utility.write_config('t4t_option', i)

                    if i != t4t_option:
                        restart = True

                    break
            t4t_ratio = int(float(self.elements['t4t0choice'].GetStringSelection()) * 100)
            self.utility.write_config("t4t_ratio", t4t_ratio)

            hours_min = self.elements['t4t2text'].GetValue()
            hours_min = hours_min.split(':')
            if len(hours_min) > 0:
                if len(hours_min) > 1:
                    self.utility.write_config("t4t_hours", hours_min[0] or 0)
                    self.utility.write_config("t4t_mins", hours_min[1] or 0)
                else:
                    self.utility.write_config("t4t_hours", hours_min[0] or 0)
                    self.utility.write_config("t4t_mins", 0)

            # give-2-get
            g2g_option = self.utility.read_config('g2g_option')
            for i in range(4):
                if self.elements['g2g%d' % i].GetValue():
                    self.utility.write_config("g2g_option", i)

                    if i != g2g_option:
                        restart = True
                    break
            g2g_ratio = int(float(self.elements['g2g0choice'].GetStringSelection()) * 100)
            self.utility.write_config("g2g_ratio", g2g_ratio)

            hours_min = self.elements['g2g2text'].GetValue()
            hours_min = hours_min.split(':')
            if len(hours_min) > 0:
                if len(hours_min) > 1:
                    self.utility.write_config("g2g_hours", hours_min[0] or 0)
                    self.utility.write_config("g2g_mins", hours_min[1] or 0)
                else:
                    self.utility.write_config("g2g_hours", hours_min[0] or 0)
                    self.utility.write_config("g2g_mins", 0)

            # Proxy settings
            old_ptype, old_server, old_auth = self.utility.session.get_libtorrent_proxy_settings()
            new_ptype = self.elements['lt_proxytype'].GetSelection()
            new_server = (self.elements['lt_proxyserver'].GetValue(), int(self.elements['lt_proxyport'].GetValue())) if self.elements['lt_proxyserver'].GetValue() and self.elements['lt_proxyport'].GetValue() else None
            new_auth = (self.elements['lt_proxyusername'].GetValue(), self.elements['lt_proxypassword'].GetValue()) if self.elements['lt_proxyusername'].GetValue() and self.elements['lt_proxypassword'].GetValue() else None
            if old_ptype != new_ptype or old_server != new_server or old_auth != new_auth:
                self.utility.session.set_libtorrent_proxy_settings(new_ptype, new_server, new_auth)
                scfg.set_libtorrent_proxy_settings(new_ptype, new_server, new_auth)

            enable_utp = self.elements['enable_utp'].GetValue()
            if enable_utp != self.utility.session.get_libtorrent_utp():
                self.utility.session.set_libtorrent_utp(enable_utp)
                scfg.set_libtorrent_utp(enable_utp)

            scfg.save(cfgfilename)

            self.utility.flush_config()

            if restart:
                dlg = wx.MessageDialog(self, "A restart is required for these changes to take effect.\nDo you want to restart Tribler now?", "Restart required", wx.ICON_QUESTION | wx.YES_NO | wx.YES_DEFAULT)
                if dlg.ShowModal() == wx.ID_YES:
                    self.guiUtility.frame.Restart()
                dlg.Destroy()
            self.EndModal(1)
            event.Skip()
        else:
            for error in errors.keys():
                if sys.platform != 'darwin':
                    self.elements[error].SetForegroundColour(wx.RED)
                self.elements[error].SetValue(errors[error])

            parentPanel = self.elements[error].GetParent()
            self.ShowPage(parentPanel, None)

    def cancelAll(self, event):
        self.EndModal(1)

    def EditClicked(self, event=None):
        dlg = ib.ImageDialog(self, get_picture_dir())
        dlg.Centre()
        if dlg.ShowModal() == wx.ID_OK:
            self.iconpath = dlg.GetFile()
            self.process_input()
        else:
            pass
        dlg.Destroy()

    def BrowseClicked(self, event=None):
        dlg = wx.DirDialog(None, "Choose download directory", style=wx.DEFAULT_DIALOG_STYLE)
        dlg.SetPath(self.defaultDLConfig.get_dest_dir())
        if dlg.ShowModal() == wx.ID_OK:
            self.elements['diskLocationCtrl'].SetForegroundColour(wx.BLACK)
            self.elements['diskLocationCtrl'].SetValue(dlg.GetPath())
        else:
            pass

    def ProxyTypeChanged(self, event=None):
        selection = self.elements['lt_proxytype'].GetStringSelection()
        self.elements['lt_proxyusername'].Enable(selection.endswith('with authentication'))
        self.elements['lt_proxypassword'].Enable(selection.endswith('with authentication'))
        self.elements['lt_proxyserver'].Enable(selection != 'None')
        self.elements['lt_proxyport'].Enable(selection != 'None')

    def _SelectAll(self, dlg, event, nrchoices):
        if event.ControlDown():
            if event.GetKeyCode() == 65:  # ctrl + a
                if dlg.allselected:
                    dlg.SetSelections([])
                else:
                    select = list(range(nrchoices))
                    dlg.SetSelections(select)
                dlg.allselected = not dlg.allselected

    def saveDefaultDownloadConfig(self, scfg):
        state_dir = self.utility.session.get_state_dir()

        # Save DownloadStartupConfig
        dlcfgfilename = get_default_dscfg_filename(state_dir)
        self.defaultDLConfig.save(dlcfgfilename)

        # Save SessionStartupConfig
        # Also change torrent collecting dir, which is by default in the default destdir
        cfgfilename = Session.get_default_config_filename(state_dir)
        defaultdestdir = self.defaultDLConfig.get_dest_dir()
        for target in [scfg, self.utility.session]:
            try:
                target.set_torrent_collecting_dir(os.path.join(defaultdestdir, STATEDIR_TORRENTCOLL_DIR))
            except:
                self._logger.exception("Could not set target torrent collecting dir")
            try:
                target.set_swift_meta_dir(os.path.join(defaultdestdir, STATEDIR_SWIFTRESEED_DIR))
            except:
                self._logger.exception("Could not set target swift meta dir")

        scfg.save(cfgfilename)

    def moveCollectedTorrents(self, old_dir, new_dir):
        def rename_or_merge(old, new, ignore=True):
            if os.path.exists(old):
                if os.path.exists(new):
                    files = os.listdir(old)
                    for file in files:
                        oldfile = os.path.join(old, file)
                        newfile = os.path.join(new, file)

                        if os.path.isdir(oldfile):
                            rename_or_merge(oldfile, newfile)

                        elif os.path.exists(newfile):
                            if not ignore:
                                os.remove(newfile)
                                os.rename(oldfile, newfile)
                        else:
                            os.rename(oldfile, newfile)
                else:
                    os.renames(old, new)

        def move(old_dir, new_dir):
            # physical move
            old_dirtf = os.path.join(old_dir, 'collected_torrent_files')
            new_dirtf = os.path.join(new_dir, 'collected_torrent_files')
            rename_or_merge(old_dirtf, new_dirtf, False)

        atexit.register(move, old_dir, new_dir)

        msg = "Please wait while we update your MegaCache..."
        busyDlg = wx.BusyInfo(msg)
        try:
            time.sleep(0.3)
            wx.Yield()
        except:
            pass

        # update db
        self.guiUtility.torrentsearch_manager.torrent_db.updateTorrentDir(os.path.join(new_dir, 'collected_torrent_files'))

        busyDlg.Destroy()

    def process_input(self):
        try:
            im = wx.Image(self.iconpath)
            if im is None:
                self.show_inputerror(self.utility.lang.get('cantopenfile'))
            else:
                if sys.platform != 'darwin':
                    bm = wx.BitmapFromImage(im.Scale(ICON_MAX_DIM, ICON_MAX_DIM), -1)
                    thumbpanel = self.elements['thumb']
                    thumbpanel.SetBitmap(bm)

                # Arno, 2008-10-21: scale image!
                sim = im.Scale(ICON_MAX_DIM, ICON_MAX_DIM)
                [thumbhandle, thumbfilename] = tempfile.mkstemp("user-thumb")
                os.close(thumbhandle)
                sim.SaveFile(thumbfilename, wx.BITMAP_TYPE_JPEG)

                f = open(thumbfilename, "rb")
                self.icondata = f.read()
                f.close()
                os.remove(thumbfilename)
        except:
            self._logger.exception("Could not read thumbnail")
            self.show_inputerror(self.utility.lang.get('iconbadformat'))

    def show_inputerror(self, txt):
        dlg = wx.MessageDialog(self, txt, self.utility.lang.get('invalidinput'), wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def __create_s1(self, tree_root, sizer):
        general_panel, gp_vsizer = create_section(self, sizer, "General")

        item_id = self._tree_ctrl.AppendItem(tree_root, "General", data=wx.TreeItemData(general_panel))

        # Tribler Profile
        gp_s1_sizer = create_subsection(general_panel, gp_vsizer, "Tribler Profile", 2)

        gp_s1_nickname_title = wx.StaticText(general_panel, -1, label="Nickname")
        gp_s1_nickname_title.SetMinSize(wx.Size(100, -1))
        gp_s1_nickname_text = wx.TextCtrl(general_panel, -1, name="myNameField", style=wx.TE_PROCESS_ENTER)
        gp_s1_sizer.Add(gp_s1_nickname_title)
        gp_s1_sizer.Add(gp_s1_nickname_text, 1, wx.EXPAND)

        gp_s1_profile_image_title = wx.StaticText(general_panel, label="Profile Image")
        gp_s1_sizer.Add(gp_s1_profile_image_title)
        gp_s1_profile_image = wx.StaticBitmap(general_panel, size=(80,80), name="thumb")
        gp_s1_profile_image_button = wx.Button(general_panel, label="Change Image", name="edit")
        gp_s1_porfile_vsizer = wx.BoxSizer(wx.VERTICAL)
        gp_s1_porfile_vsizer.Add(gp_s1_profile_image, 0, wx.LEFT, 1)
        gp_s1_porfile_vsizer.Add(gp_s1_profile_image_button)
        gp_s1_sizer.Add(gp_s1_porfile_vsizer, 0, wx.TOP, 3)

        # Download Location
        gp_s2_sizer = create_subsection(general_panel, gp_vsizer, "Download Location", 1)

        gp_s2_label = wx.StaticText(general_panel, label="Save files to:")
        gp_s2_sizer.Add(gp_s2_label)
        gp_s2_hsizer = wx.BoxSizer(wx.HORIZONTAL)
        gp_s2_text = wx.TextCtrl(general_panel, name="diskLocationCtrl", style=wx.TE_PROCESS_ENTER)
        gp_s2_hsizer.Add(gp_s2_text, 1, wx.ALIGN_CENTER_VERTICAL)
        gp_s2_button = wx.Button(general_panel, label="Browse", name="browse")
        gp_s2_hsizer.Add(gp_s2_button)
        gp_s2_sizer.Add(gp_s2_hsizer, 0, wx.EXPAND)
        gp_s2_checkbox = wx.CheckBox(general_panel,
            label="Let me choose a location for every download", name="diskLocationChoice")
        gp_s2_checkbox.SetValue(False)
        gp_s2_sizer.Add(gp_s2_checkbox)

        # Minimize
        gp_s3_sizer = create_subsection(general_panel, gp_vsizer, "Minimize", 1)

        gp_s3_checkbox = wx.CheckBox(general_panel, label="Minimize to tray", name="minimize_to_tray")
        gp_s3_checkbox.SetValue(False)
        gp_s3_sizer.Add(gp_s3_checkbox)

        return general_panel, item_id

    def __create_s2(self, tree_root, sizer):
        conn_panel, cn_vsizer = create_section(self, sizer, "Connection")

        item_id = self._tree_ctrl.AppendItem(tree_root, "Connection", data=wx.TreeItemData(conn_panel))

        # Firewall-status
        cn_s1_sizer = create_subsection(conn_panel, cn_vsizer, "Firewall-status", 2, 3)
        cn_s1_port_label = wx.StaticText(conn_panel, label="Current port")
        cn_s1_port_label.SetMinSize(wx.Size(80, -1))
        cn_s1_sizer.Add(cn_s1_port_label)
        cn_s1_port_text = wx.TextCtrl(conn_panel, name="firewallValue", style=wx.TE_PROCESS_ENTER)
        cn_s1_sizer.Add(cn_s1_port_text)

        cn_s1_status_label = wx.StaticText(conn_panel, label="Status")
        cn_s1_sizer.Add(cn_s1_status_label)
        cn_s1_status_text = wx.StaticText(conn_panel, name="firewallStatusText")
        cn_s1_sizer.Add(cn_s1_status_text)

        # BitTorrent proxy settings
        cn_s2_sizer = create_subsection(conn_panel, cn_vsizer, "BitTorrent proxy settings", 2, 3)
        cn_s2_type_label = wx.StaticText(conn_panel, label="Type")
        cn_s2_sizer.Add(cn_s2_type_label)
        cn_s2_type_choice = wx.Choice(conn_panel, name="lt_proxytype")
        cn_s2_type_choice.AppendItems(["None", "Socks4", "Socks5",
            "Socks5 with authentication", "HTTP", "HTTP with authentication"])
        cn_s2_sizer.Add(cn_s2_type_choice)

        cn_s2_server_label = wx.StaticText(conn_panel, label="Server")
        cn_s2_sizer.Add(cn_s2_server_label, 0, wx.LEFT)
        cn_s2_server_text = wx.TextCtrl(conn_panel, name="lt_proxyserver", style=wx.TE_PROCESS_ENTER)
        cn_s2_sizer.Add(cn_s2_server_text, 0, wx.EXPAND)

        cn_s2_port_label = wx.StaticText(conn_panel, label="Port")
        cn_s2_sizer.Add(cn_s2_port_label, 0, wx.LEFT)
        cn_s2_port_text = wx.TextCtrl(conn_panel, name="lt_proxyport", style=wx.TE_PROCESS_ENTER)
        cn_s2_sizer.Add(cn_s2_port_text, 0, wx.EXPAND)

        cn_s2_username_label = wx.StaticText(conn_panel, label="Username")
        cn_s2_sizer.Add(cn_s2_username_label, 0, wx.LEFT)
        cn_s2_username_text = wx.TextCtrl(conn_panel, name="lt_proxyusername", style=wx.TE_PROCESS_ENTER)
        cn_s2_sizer.Add(cn_s2_username_text, 0, wx.EXPAND)

        cn_s2_password_label = wx.StaticText(conn_panel, label="Password")
        cn_s2_sizer.Add(cn_s2_password_label, 0, wx.LEFT)
        cn_s2_password_text = wx.TextCtrl(conn_panel, name="lt_proxypassword",
            style=wx.TE_PROCESS_ENTER | wx.TE_PASSWORD)
        cn_s2_sizer.Add(cn_s2_password_text, 0, wx.EXPAND)

        # BitTorrent features
        cn_s3_sizer = create_subsection(conn_panel, cn_vsizer, "BitTorrent features", 1)
        cn_s3_check = wx.CheckBox(conn_panel, size=(200,50), name="enable_utp",
            label="Enable bandwidth management (uTP)")
        cn_s3_sizer.Add(cn_s3_check, 0, wx.EXPAND)

        return conn_panel, item_id

    def __create_s3(self, tree_root, sizer):
        bandwidth_panel, bp_vsizer = create_section(self, sizer, "Bandwidth")

        item_id = self._tree_ctrl.AppendItem(tree_root, "Bandwidth", data=wx.TreeItemData(bandwidth_panel))

        # Bandwidth Limits
        bp_s1_sizer = create_subsection(bandwidth_panel, bp_vsizer, "Bandwidth Limits", 1)
        bp_s1_limitupload_label = wx.StaticText(bandwidth_panel, label="Limit upload rate")
        bp_s1_sizer.Add(bp_s1_limitupload_label)
        bp_s1_hsizer1 = wx.BoxSizer(wx.HORIZONTAL)
        bp_s1_p1_text = wx.TextCtrl(bandwidth_panel, name="uploadCtrl")
        bp_s1_hsizer1.Add(bp_s1_p1_text)
        bp_s1_p1_label = wx.StaticText(bandwidth_panel, label="KB/s")
        bp_s1_hsizer1.Add(bp_s1_p1_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 3)
        bp_s1_hsizer1.AddStretchSpacer(1)
        # up buttons
        for btn_label1 in ("0", "50", "100", "unlimited"):
            bp_s1_p1_btn = wx.Button(bandwidth_panel, label=btn_label1, style=wx.BU_EXACTFIT)
            bp_s1_p1_btn.Bind(wx.EVT_BUTTON, lambda event: self.setUp(btn_label1, event))
            bp_s1_hsizer1.Add(bp_s1_p1_btn)
        bp_s1_sizer.Add(bp_s1_hsizer1, 0, wx.EXPAND)

        bp_s1_limitdownload_label = wx.StaticText(bandwidth_panel, label="Limit download rate")
        bp_s1_sizer.Add(bp_s1_limitdownload_label)
        bp_s1_hsizer2 = wx.BoxSizer(wx.HORIZONTAL)
        bp_s1_p2_text = wx.TextCtrl(bandwidth_panel, name="downloadCtrl")
        bp_s1_hsizer2.Add(bp_s1_p2_text)
        bp_s1_p2_label = wx.StaticText(bandwidth_panel, label="KB/s")
        bp_s1_hsizer2.Add(bp_s1_p2_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 3)
        bp_s1_hsizer2.AddStretchSpacer(1)
        # down buttons
        for btn_label2 in ("75", "300", "600", "unlimited"):
            bp_s1_p2_btn = wx.Button(bandwidth_panel, label=btn_label2, style=wx.BU_EXACTFIT)
            bp_s1_p2_btn.Bind(wx.EVT_BUTTON, lambda event: self.setDown(btn_label2, event))
            bp_s1_hsizer2.Add(bp_s1_p2_btn)
        bp_s1_sizer.Add(bp_s1_hsizer2, 0, wx.EXPAND)

        return bandwidth_panel, item_id

    def __create_s4(self, tree_root, sizer):
        seeding_panel, sd_vsizer = create_section(self, sizer, "Seeding")

        item_id = self._tree_ctrl.AppendItem(tree_root, "Seeding", data=wx.TreeItemData(seeding_panel))

        # BitTorrent-peers
        sd_s1_sizer = create_subsection(seeding_panel, sd_vsizer, "BitTorrent-peers", 2)
        sd_s1_radio_btn1 = wx.RadioButton(seeding_panel, label="Seed until UL/DL ratio >",
            name="t4t0", style=wx.RB_GROUP)
        sd_s1_sizer.Add(sd_s1_radio_btn1, 0, wx.ALIGN_CENTER_VERTICAL)
        sd_s1_choice = wx.Choice(seeding_panel, name="t4t0choice")
        sd_s1_choice.AppendItems(["0.5", "0.75", "1.0", "1.5", "2.0", "3.0", "5.0"])
        sd_s1_sizer.Add(sd_s1_choice, 0, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)

        sd_s1_radio_btn2 = wx.RadioButton(seeding_panel,
            label="Unlimited seeding", name="t4t1")
        sd_s1_sizer.Add(sd_s1_radio_btn2, 0, wx.ALIGN_CENTER_VERTICAL)
        sd_s1_sizer.AddStretchSpacer()

        sd_s1_radio_btn3 = wx.RadioButton(seeding_panel,
            label="Seeding for (hours:minutes)", name="t4t2")
        sd_s1_sizer.Add(sd_s1_radio_btn3, 0, wx.ALIGN_CENTER_VERTICAL)
        sd_s1_text = wx.TextCtrl(seeding_panel, name="t4t2text",
            style=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        sd_s1_sizer.Add(sd_s1_text)

        sd_s1_radio_btn4 = wx.RadioButton(seeding_panel,
            label="No seeding", name="t4t3")
        sd_s1_sizer.Add(sd_s1_radio_btn4, 0, wx.ALIGN_CENTER_VERTICAL)

        # Tribler-peers
        sd_s2_sizer = create_subsection(seeding_panel, sd_vsizer, "Tribler-peers", 2)
        sd_s2_radio_btn1 = wx.RadioButton(seeding_panel, label="Seed to peers with UL/DL ratio",
            name="g2g0", style=wx.RB_GROUP)
        sd_s2_sizer.Add(sd_s2_radio_btn1, 0, wx.ALIGN_CENTER_VERTICAL)
        sd_s2_choice = wx.Choice(seeding_panel, name="g2g0choice")
        sd_s2_choice.AppendItems(["0.5", "0.75", "1.0", "1.5", "2.0", "3.0", "5.0"])
        sd_s2_sizer.Add(sd_s2_choice, 0, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)

        sd_s2_radio_btn2 = wx.RadioButton(seeding_panel,
            label="Unlimited seeding (Boost your reputation)", name="g2g1")
        sd_s2_sizer.Add(sd_s2_radio_btn2, 0, wx.ALIGN_CENTER_VERTICAL)
        sd_s2_sizer.AddStretchSpacer(1)

        sd_s2_radio_btn3 = wx.RadioButton(seeding_panel,
            label="Seeding for (hours:minutes)", name="g2g2")
        sd_s2_sizer.Add(sd_s2_radio_btn3, 0, wx.ALIGN_CENTER_VERTICAL)
        sd_s2_text = wx.TextCtrl(seeding_panel, name="g2g2text",
            style=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        sd_s2_sizer.Add(sd_s2_text)

        sd_s2_radio_btn4 = wx.RadioButton(seeding_panel,
            label="No seeding", name="g2g3")
        sd_s2_sizer.Add(sd_s2_radio_btn4, 0, wx.ALIGN_CENTER_VERTICAL)

        sd_vsizer.AddStretchSpacer(1)

        sd_faq_text = wx.StaticText(seeding_panel, label="Why differ between 'normal' BitTorrent and Tribler-peers?\nBecause between Tribler-peers you will build up a repuation.\nThis is not the case for 'normal' BitTorrent-peers.")
        sd_vsizer.Add(sd_faq_text)

        return seeding_panel, item_id

    def __create_s5(self, tree_root, sizer):
        exp_panel, exp_vsizer = create_section(self, sizer, "Experimental")

        item_id = self._tree_ctrl.AppendItem(tree_root, "Experimental", data=wx.TreeItemData(exp_panel))

        # Web UI
        exp_s1_sizer = create_subsection(exp_panel, exp_vsizer, "Web UI", 2, 3)
        exp_s1_check = wx.CheckBox(exp_panel, label="Enable webUI", name="use_webui")
        exp_s1_sizer.Add(exp_s1_check, 0, wx.EXPAND)
        exp_s1_sizer.AddStretchSpacer()
        exp_s1_port_label = wx.StaticText(exp_panel, label="Current port")
        exp_s1_port_label.SetMinSize(wx.Size(100, -1))
        exp_s1_sizer.Add(exp_s1_port_label, 0, wx.ALIGN_CENTER_VERTICAL)
        exp_s1_port_text = wx.TextCtrl(exp_panel, name="webui_port", style=wx.TE_PROCESS_ENTER)
        exp_s1_sizer.Add(exp_s1_port_text)

        exp_s1_faq_text = wx.StaticText(exp_panel, label="The Tribler webUI implements the same API as uTorrent.\nThus all uTorrent remotes are compatible with it.\n\nFurthermore, we additionally allow you to control Tribler using your Browser. Go to http://localhost:PORT/gui to view your \ndownloads in the browser.")
        exp_vsizer.Add(exp_s1_faq_text, 0, wx.EXPAND | wx.TOP, 10)

        return exp_panel, item_id

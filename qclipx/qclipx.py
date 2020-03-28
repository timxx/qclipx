# -*- coding:utf-8 -*-
# *
# * Copyright (c) 2020 Weitian Leung
# *
# * This file is part of qclipx.
# *
# * This file is distributed under the MIT License.
# * See the LICENSE file for details.
# *
#

from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtCore import *
from zipfile import (ZipFile, BadZipFile)
from io import BytesIO

import sys
import re
import argparse
import tempfile
import shutil
import math


is_mac = (sys.platform == "darwin")

supported_images = ["BMP", "GIF", "JPG", "JPEG", "MNG",
                    "PNG", "PBM", "PGM", "PPM", "TIFF",
                    "XBM", "XPM", "SVG", "TGA", "JFIF"]

img_mime_re = re.compile('^application/x-qt-windows-mime;value="([a-zA-Z]+)"$')
qt_mime_re = re.compile('^application/x-qt-windows-mime;value="(.*)"$')

tmp_dir = tempfile.mkdtemp()


def defaultDpiX():
    screen = qApp.primaryScreen()
    if screen:
        return round(screen.logicalDotsPerInchX())

    return 96.0


def dpiScaled(value):
    if isinstance(value, int) or isinstance(value, float):
        # from Qt, on mac the DPI is always 72
        if is_mac:
            return value
        return value * defaultDpiX() / 96.0
    elif isinstance(value, QSize):
        w = dpiScaled(value.width())
        h = dpiScaled(value.height())
        return QSize(w, h)
    elif isinstance(value, QSizeF):
        w = dpiScaled(value.width())
        h = dpiScaled(value.height())
        return QSizeF(w, h)
    elif isinstance(value, QPoint):
        x = dpiScaled(value.x())
        y = dpiScaled(value.y())
        return QPoint(x, y)
    elif isinstance(value, QPointF):
        x = dpiScaled(value.x())
        y = dpiScaled(value.y())
        return QPointF(x, y)
    elif isinstance(value, QMargins):
        l = dpiScaled(value.left())
        t = dpiScaled(value.top())
        r = dpiScaled(value.right())
        b = dpiScaled(value.bottom())
        return QMargins(l, t, r, b)
    elif isinstance(value, QMarginsF):
        l = dpiScaled(value.left())
        t = dpiScaled(value.top())
        r = dpiScaled(value.right())
        b = dpiScaled(value.bottom())
        return QMarginsF(l, t, r, b)
    elif isinstance(value, QRect):
        l = dpiScaled(value.left())
        t = dpiScaled(value.top())
        r = dpiScaled(value.right())
        b = dpiScaled(value.bottom())
        return QRect(l, t, r, b)
    elif isinstance(value, QRectF):
        l = dpiScaled(value.left())
        t = dpiScaled(value.top())
        r = dpiScaled(value.right())
        b = dpiScaled(value.bottom())
        return QRectF(l, t, r, b)
    elif isinstance(value, tuple):
        return dpiScaled(value[0]), dpiScaled(value[1])
    else:
        print("Unspported type")
        return value


def decode_data(data):
    encodings = ['utf-8', 'utf-16', 'latin1']
    for e in encodings:
        try:
            return str(data, e)
        except UnicodeDecodeError:
            continue
    return data


def is_image_mime(mime):
    if mime.startswith("image/"):
        return True
    match = img_mime_re.search(mime)
    if match and match.group(1) in supported_images:
        return True
    return False


# FIXME:
def is_zip_data(data):
    if data.startsWith(b'PK\003\004'):
        return True
    # empty zip
    if data.startsWith(b'PK\005\006'):
        return True
    return False


class MyDockWidget(QDockWidget):
    mimeChanged = Signal([str])

    def __init__(self, parent=None):
        super(MyDockWidget, self).__init__(parent)
        self.setFeatures(QDockWidget.DockWidgetMovable)

        self.cbMime = QComboBox()
        self.cbMime.currentIndexChanged['QString'].connect(self.mimeChanged)
        self.setWidget(self.cbMime)

        QApplication.clipboard().dataChanged.connect(self._init_mime)
        self._init_mime()

    def _init_mime(self):
        curMime = self.cbMime.currentText()

        self.cbMime.clear()
        clipboard = QApplication.clipboard()
        for fmt in clipboard.mimeData().formats():
            self.cbMime.addItem(fmt)

        # set to the old one
        if self.cbMime.count() and curMime:
            index = self.cbMime.findText(curMime)
            if index != -1 and index != self.cbMime.currentIndex():
                self.cbMime.setCurrentIndex(index)
                self.mimeChanged.emit(curMime)

    def currentMime(self):
        return self.cbMime.currentText()


class MyScrollArea(QScrollArea):
    def __init__(self, widget, parent=None):
        super(MyScrollArea, self).__init__(parent)

        self.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.setWidgetResizable(True)
        self.setWidget(widget)


class MyTreeWidget(QTreeWidget):
    fileClicked = Signal([str])
    TypeRole = Qt.UserRole + 1
    FileType = 1
    FolderType = 2

    def __init__(self, parent=None):
        super(MyTreeWidget, self).__init__(parent)

        header = QTreeWidgetItem()
        header.setText(0, "Name")
        header.setText(1, "Size")
        header.setText(2, "Type")
        header.setText(3, "Modified")
        self.setHeaderItem(header)
        self.setSortingEnabled(True)
        self.sortByColumn(2, Qt.DescendingOrder)

        self.itemDoubleClicked.connect(self._onItemDoubleClicked)

    def showZip(self, infolist):
        for f in infolist:
            if '/' in f.filename:  # with folder
                index = f.filename.index('/')
                top_folder = f.filename[0: index]
                sub_path = f.filename[index + 1:]
                self._addFolderItem(top_folder, sub_path, f)
            else:  # top file name only
                self._addFileItem(f)

    def _addFileItem(self, file_info, parent=None):
        item = QTreeWidgetItem()
        index = file_info.filename.rfind('/')
        file_name = file_info.filename[index +
                                       1:] if index > 0 else file_info.filename
        item.setText(0, file_name)
        item.setText(3, self._prettyDate(file_info.date_time))

        item.setData(0, MyTreeWidget.TypeRole, MyTreeWidget.FileType)
        item.setText(1, self._prettySize(file_info.file_size))
        item.setText(2, "File")

        icon = QFileIconProvider()
        item.setIcon(0, icon.icon(QFileIconProvider.File))

        if parent:
            parent.addChild(item)
        else:
            self.addTopLevelItem(item)

    def _addFolderItem(self, folder, subpath, file_info, parent=None):
        # find if already added this folder
        found = False
        full_path = self._makeFullPath(folder, parent)
        items = self.findItems(folder, Qt.MatchExactly | Qt.MatchRecursive)
        for item in items:
            if item.data(0, MyTreeWidget.TypeRole) != MyTreeWidget.FolderType:
                continue

            cur_path = self._makeFullPath(item.text(0), item.parent())
            if cur_path == full_path:
                found = True
                break

        if not found:
            item = QTreeWidgetItem()
            item.setText(0, folder)
            item.setData(0, MyTreeWidget.TypeRole, MyTreeWidget.FolderType)
            item.setText(2, "Folder")

            icon = QFileIconProvider()
            item.setIcon(0, icon.icon(QFileIconProvider.Folder))

            if parent:
                parent.addChild(item)
            else:
                self.addTopLevelItem(item)

        if not subpath:
            return

        index = subpath.find('/')
        if index > 0:
            folder = subpath[0: index]
            subpath = subpath[index + 1:]
            self._addFolderItem(folder, subpath, file_info, item)
        else:
            self._addFileItem(file_info, item)

    def _makeFullPath(self, path, parent):
        full_path = path
        while parent is not None:
            full_path = parent.text(0) + "/" + full_path
            parent = parent.parent()

        return full_path

    def _prettySize(self, size):
        if size < 1024:
            return "%d B" % size

        if size < 1024 * 1024:
            kb = size / 1024
            return "%.2f KB" % kb

        if size < 1024 * 1024 * 1024:
            mb = size / 1024 / 1024
            return "%.2f MB" % mb

        gb = size / 1024 / 1024 / 1024
        return "%.2f GB" % gb

    def _prettyDate(self, date):
        return "%d/%02d/%02d, %02d:%02d:%02d" % (date[0], date[1], date[2],
                                                 date[3], date[4], date[5])

    def _onItemDoubleClicked(self, item, col):
        if item.data(0, MyTreeWidget.TypeRole) != MyTreeWidget.FileType:
            return

        path = self._makeFullPath(item.text(0), item.parent())
        self.fileClicked.emit(path)


class MyChunk:
    def __init__(self):
        self._data = []
        self._readed = False

    def __len__(self):
        return len(self._data)

    def __getitem__(self, index):
        return self._data[index]

    def __iter__(self):
        return iter(self._data)

    def dataReaded(self):
        return self._readed

    def setData(self, data):
        self._readed = True
        self._data = list(self._createHexList(data.toHex().toUpper()))

    def _createHexList(self, data):
        for i in range(0, len(data), 2):
            yield data.data()[i: i + 2]


class MyChunks:
    def __init__(self, data, hexPerRow):
        self._data = data
        self._hexPerRow = hexPerRow
        self._chunks = []
        self._createEmptyChunks()

    def __len__(self):
        return len(self._chunks)

    def __getitem__(self, index):
        chunk = self._chunks[index]
        if not chunk.dataReaded():
            data = self._data.mid(index * self._hexPerRow, self._hexPerRow)
            chunk.setData(data)

        return chunk

    def __iter__(self):
        return iter(self._chunks)

    def _createEmptyChunks(self):
        size = math.ceil(self._data.size() / self._hexPerRow)
        self._chunks = [MyChunk() for i in range(size)]


class MyHexView(QAbstractScrollArea):
    """A Simple Hex View"""

    def __init__(self, parent=None):
        super(MyHexView, self).__init__(parent)

        # use fixed font for better look in ascii view
        font = self._getFixedFont()
        self.setFont(font)

        self._chunks = []
        self._hexPerRow = 16  # each line contains 16 hex
        self._charW = self.fontMetrics().horizontalAdvance('F')
        self._charH = self.fontMetrics().height() + dpiScaled(3)  # extra spaces
        self._adrSepX = self._charW * 9  # address area separator
        self._hexStartX = self._adrSepX + self._charW
        self._hexSepX = self._hexStartX + \
            self._charW * (4 * self._hexPerRow - 1)
        self._asciiStartX = self._hexSepX + self._charW

        # cursor position, (row, col) in _chunks
        self._cursorPos = QPoint(0, 0)
        # active in ascii or not
        self._isInAscii = False

        # selection end point, (-1, -1) means no selection
        self._selEndPos = QPoint(-1, -1)

    def showData(self, data):
        self._chunks = MyChunks(data, self._hexPerRow)
        self._cursorPos = QPoint(0, 0)
        self._selEndPos = QPoint(-1, -1)
        self.viewport().update()
        self._adjust()

    def mouseMoveEvent(self, event):
        if len(self._chunks) > 0 and event.buttons() & Qt.LeftButton:
            if self._selEndPos != QPoint(-1, -1):
                self._updateSelection()

            self._selEndPos, _ = self._posToRC(event.pos())
            self._updateSelection()

    def mousePressEvent(self, event):
        if len(self._chunks) == 0:
            return
        if self._selEndPos != QPoint(-1, -1):
            self._updateSelection()
            self._selEndPos = QPoint(-1, -1)

        self._updateCursor()  # clear the old cursor
        self._cursorPos, self._isInAscii = self._posToRC(event.pos())
        self._updateCursor()

    def resizeEvent(self, event):
        self._adjust()

    def paintEvent(self, event):
        row = len(self._chunks)
        if row == 0:
            return
        painter = QPainter(self.viewport())
        # row in viewport, must be same as _adjust
        rowShown = int((self.viewport().height() -
                        self._charH / 4) / self._charH)
        if rowShown > row:
            rowShown = row

        # horizontal offset
        offsetX = self.horizontalScrollBar().value() * self._charW
        # vertical offset
        offsetY = self.verticalScrollBar().value() * self._charH

        # draw the selection
        # might optimize in another way :(
        if self._selEndPos != QPoint(-1, -1):
            for x in (True, False):
                rects = self._rcToRect(self._cursorPos, self._selEndPos, x)
                for rc in rects:
                    painter.fillRect(rc, QColor(135, 170, 215))

        self._drawAdr(painter, rowShown, offsetX)
        self._drawHex(painter, rowShown, offsetX)

        # draw cursor if no selection
        if self._selEndPos == QPoint(-1, -1):
            self._drawCursor(painter, offsetX, offsetY)

    def _drawAdr(self, painter, row, offsetX):
        painter.save()

        painter.setPen(QColor(149, 22, 22))
        x = 0
        y = self._charH
        n = self.verticalScrollBar().value() * self._hexPerRow
        for i in range(0, row):
            painter.drawText(x - offsetX, y, "%08X" % n)
            y += self._charH
            n += self._hexPerRow

        # draw separator
        painter.setPen(QColor(0, 100, 0))
        painter.drawLine(self._adrSepX - offsetX, 0,
                         self._adrSepX - offsetX, row * self._charH)

        painter.restore()

    def _drawHex(self, painter, row, offsetX):
        """ draw hex data and ascii """
        painter.save()

        x = self._hexStartX
        asciiX = self._asciiStartX
        y = self._charH
        w = self._charW * 4
        r = self.verticalScrollBar().value()
        for i in range(0, row):
            n = 1
            for hex in self._chunks[i + r]:
                if n % 2 == 0:
                    painter.setPen(QColor(0, 0, 255))
                else:
                    painter.setPen(QColor(0, 0, 0))
                n += 1
                painter.drawText(x - offsetX, y, str(hex, 'ascii'))
                self._drawAscii(painter, asciiX - offsetX, y, hex)
                x += w
                asciiX += self._charW
            y += self._charH
            x = self._hexStartX
            asciiX = self._asciiStartX

        # separator
        painter.setPen(QColor(0, 100, 0))
        painter.drawLine(self._hexSepX - offsetX, 0,
                         self._hexSepX - offsetX, row * self._charH)

        painter.restore()

    def _drawAscii(self, painter, x, y, hex):
        painter.save()

        n = int(hex, 16)
        # invisible char use '.' instead
        if n > 0x7E or n < 0x20:
            ch = '.'
        else:
            ch = chr(n)

        painter.setPen(QColor(0, 0, 0))
        painter.drawText(x, y, ch)

        painter.restore()

    def _drawCursor(self, painter, offsetX, offsetY):
        painter.save()

        color = QColor(255, 0, 0)
        if not self.isActiveWindow():
            color = QColor(128, 128, 128)
        painter.setPen(color)
        pos = self._rcToPos(self._cursorPos, self._isInAscii)
        x = pos.x() - offsetX
        y = pos.y() - offsetY
        painter.drawLine(x, y, x, y + self._charH)

        # under line
        pen = QPen(color)
        pen.setWidth(dpiScaled(2))
        painter.setPen(pen)

        x = pos.x() - offsetX + dpiScaled(1)
        y = pos.y() + self._charH - offsetY

        w = {True: self._charW, False: 2 * self._charW}
        painter.drawLine(x, y, x + w[self._isInAscii], y)

        pos = self._rcToPos(self._cursorPos, not self._isInAscii)
        x = pos.x() - offsetX + dpiScaled(1)
        y = pos.y() + self._charH - offsetY
        painter.drawLine(x, y, x + w[not self._isInAscii], y)

        painter.restore()

    def _adjust(self):
        width = self._asciiStartX  # at least need this
        if len(self._chunks) > 0:
            width += len(self._chunks[0]) * self._charW

        self.horizontalScrollBar().setRange(0, width - self.viewport().width())
        self.horizontalScrollBar().setPageStep(self.viewport().width())

        # leave some spaces for the last line
        rowShown = int((self.viewport().height() -
                        self._charH / 4) / self._charH)
        totalRow = len(self._chunks)
        self.verticalScrollBar().setRange(0, totalRow - rowShown)
        self.verticalScrollBar().setPageStep(rowShown)

    def _isFixedPitch(self, font):
        fontInfo = QFontInfo(font)
        return fontInfo.fixedPitch()

    def _getFixedFont(self):
        font = QFont("Monospace")
        if self._isFixedPitch(font):
            return font

        font.setStyleHint(QFont.Monospace)
        if self._isFixedPitch(font):
            return font

        font.setStyleHint(QFont.TypeWriter)
        if self._isFixedPitch(font):
            return font

        # for Windows
        font.setFamily("Courier")
        return font

    def _rcToPos(self, rcPoint, isAscii=False):
        """ convert (row, col) to client rect position """
        if isAscii:
            x = self._asciiStartX + rcPoint.x() * self._charW
        else:
            x = self._hexStartX + rcPoint.x() * 4 * self._charW
        y = rcPoint.y() * self._charH

        return QPoint(x - dpiScaled(1), y + dpiScaled(4))

    def _posToRC(self, pos):
        """return (row, col) and whether is in ascii view"""
        isAscii = False
        if pos.x() >= self._hexSepX:
            isAscii = True
            c = int((pos.x() - self._asciiStartX) / self._charW)
        else:
            c = int((pos.x() + 2 * self._charW -
                     self._hexStartX) / self._charW / 4)

        r = int((pos.y() - dpiScaled(5)) / self._charH) + \
            self.verticalScrollBar().value()
        row = len(self._chunks)

        if r >= row:
            r = row - 1
            if c < 0:
                c = 0
            else:
                c = len(self._chunks[r]) - 1
        elif r < 0:
            r = 0

        if c >= len(self._chunks[r]):
            c = len(self._chunks[r]) - 1
        elif c < 0:
            c = 0

        return QPoint(c, r), isAscii

    def _normalRC(self, rc1, rc2):
        begin = rc1
        end = rc2

        if rc1.y() == rc2.y():
            if rc1.x() > rc2.x():
                begin = rc2
                end = rc1
        elif rc1.y() > rc2.y():
            begin = rc2
            end = rc1

        return begin, end

    def _calcWidth(self, n, isInAscii):
        if isInAscii:
            return (n + 1) * self._charW
        return (2 * n + 1) * 2 * self._charW

    def _rcToRect(self, begin, end=None, isInAscii=False):
        """calc rects from begin to end"""
        if end == None:
            end = begin

        startX = {True: self._asciiStartX, False: self._hexStartX}
        offsetX = self.horizontalScrollBar().value() * self._charW + dpiScaled(1)
        offsetY = self.verticalScrollBar().value() * self._charH - dpiScaled(4)
        offsetW = dpiScaled(2)
        offsetH = dpiScaled(1)

        posBegin, posEnd = self._normalRC(begin, end)

        if isInAscii:
            x = self._asciiStartX + posBegin.x() * self._charW
        else:
            x = self._hexStartX + posBegin.x() * 4 * self._charW
        y = posBegin.y() * self._charH

        # the same row
        if posEnd.y() == posBegin.y():
            w = self._calcWidth(posEnd.x() - posBegin.x(), isInAscii)

            return [QRect(x - offsetX, y - offsetY, w + offsetW, self._charH + offsetH)]

        # first row
        w = self._calcWidth(self._hexPerRow - posBegin.x() - 1, isInAscii)
        rects = [QRect(x - offsetX, y - offsetY, w +
                       offsetW, self._charH + offsetH)]

        # middle rows
        x = startX[isInAscii]
        r = posBegin.y() + 1
        if r < posEnd.y():
            y = r * self._charH
            w = self._calcWidth(self._hexPerRow - 1, isInAscii)
            h = self._charH * (posEnd.y() - r)
            rects.append(QRect(x - offsetX, y - offsetY,
                               w + offsetW, h + offsetH))

        # the last row
        w = self._calcWidth(posEnd.x(), isInAscii)
        y = posEnd.y() * self._charH
        rects.append(QRect(x - offsetX, y - offsetY,
                           w + offsetW, self._charH + offsetH))

        return rects

    def _updateCursor(self):
        for x in (True, False):
            rect = self._rcToRect(self._cursorPos, isInAscii=x)
            self.viewport().update(rect[0])

    def _updateSelection(self):
        for x in (True, False):
            rects = self._rcToRect(self._cursorPos, self._selEndPos, x)
            for rc in rects:
                self.viewport().update(rc)


class MyCentralWidget(QTabWidget):
    def __init__(self, parent=None):
        super(MyCentralWidget, self).__init__(parent)

        self.tabBar().hide()

        self.editor = QTextEdit()

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self.treeWidget = MyTreeWidget()
        self.treeWidget.fileClicked.connect(self._onFileClicked)

        self.hexView = MyHexView()

        self.addTab(self.editor, "Text Browser")
        self.addTab(MyScrollArea(self.label, self), "Image Viewer")
        self.addTab(self.treeWidget, "Zip Viewer")
        self.addTab(self.hexView, "Hex Viewer")

    def showMime(self, mime, viewMode=0):
        clipboard = QApplication.clipboard()
        data = clipboard.mimeData().data(mime)

        if viewMode == 1:  # Raw Data
            self.setCurrentIndex(0)
            self.editor.setPlainText(str(data, 'latin1').replace('\00', '\01'))
            return
        elif viewMode == 2:  # Hex View
            self.setCurrentIndex(3)
            self.hexView.showData(data)
            return
        elif is_image_mime(mime):
            self.setCurrentIndex(1)
            image = QImage.fromData(data, mime)
            self.label.setPixmap(QPixmap.fromImage(image))
            return
        elif is_zip_data(data):
            try:
                self.zipfile = ZipFile(BytesIO(data))
                self._show_zip_data(self.zipfile)
                return
            except BadZipFile:
                pass

        # all other goes here
        self.setCurrentIndex(0)
        text = decode_data(data).replace('\00', '\01')
        self.editor.setText(text)

    def setMime(self, mime, viewMode):
        clipboard = QApplication.clipboard()
        oldMimeData = clipboard.mimeData()
        data = None
        if viewMode == 0 or viewMode == 1:
            data = self.editor.toPlainText().encode("utf-8")

        mime = qt_mime_re.sub("\\1", mime)
        if data:
            newMimeData = QMimeData()
            for fmt in oldMimeData.formats():
                fmt = qt_mime_re.sub("\\1", fmt)
                if fmt != mime:
                    newMimeData.setData(fmt, oldMimeData.data(fmt))
                else:
                    newMimeData.setData(mime, data)
            clipboard.setMimeData(newMimeData)

    def _show_zip_data(self, file):
        self.setCurrentIndex(2)
        self.treeWidget.clear()
        self.treeWidget.showZip(file.infolist())

    def _onFileClicked(self, file):
        path = self.zipfile.extract(file, tmp_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class MyWindow(QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()

        self.viewMode = 0
        self.resize(dpiScaled(QSize(760, 480)))
        self.setWindowTitle("QClipX")

        self._createMenus()

        self.dockWidget = MyDockWidget(self)
        self.dockWidget.mimeChanged.connect(self._onMimeChanged)
        self.addDockWidget(Qt.TopDockWidgetArea, self.dockWidget)

        self.centralWidget = MyCentralWidget()
        self.setCentralWidget(self.centralWidget)

        self._refresh()

    def _createMenus(self):
        fileMenu = self.menuBar().addMenu("&File")

        acSave = fileMenu.addAction("&Save")
        acSave.triggered.connect(self._onActionSaveTriggered)
        fileMenu.addSeparator()

        acSaveToClipboard = fileMenu.addAction("Save to clipboard")
        acSaveToClipboard.triggered.connect(
            self._onActionSaveToClipboardTriggered)
        fileMenu.addSeparator()

        acQuit = QAction("&Quit", self)
        acQuit.triggered.connect(QCoreApplication.instance().quit)
        fileMenu.addAction(acQuit)

        viewMenu = self.menuBar().addMenu("&View")

        acVisual = QAction("&Visual", self)
        acVisual.setCheckable(True)
        acVisual.triggered.connect(self._onActionVisualTriggered)
        viewMenu.addAction(acVisual)

        acRawData = QAction("&Raw Data", self)
        acRawData.setCheckable(True)
        acRawData.triggered.connect(self._onActionRawDataTriggered)
        viewMenu.addAction(acRawData)

        acHexView = QAction("&Hex View", self)
        acHexView.setCheckable(True)
        acHexView.triggered.connect(self._onActionHexViewTriggered)
        viewMenu.addAction(acHexView)

        viewGroup = QActionGroup(self)
        viewGroup.addAction(acVisual)
        viewGroup.addAction(acRawData)
        viewGroup.addAction(acHexView)
        acVisual.setChecked(True)

    def _onActionSaveTriggered(self):
        mime = self.dockWidget.currentMime()
        if len(mime) == 0:
            print("No mime selected")
            return

        file, _ = QFileDialog.getSaveFileName(self, "Save '%s'" % mime)
        if len(file) == 0:
            return

        out = QFile(file)
        if not out.open(QFile.WriteOnly):
            print("Can't save file")
            return

        clipboard = QApplication.clipboard()
        out.write(clipboard.mimeData().data(mime))
        out.close()

    def _onActionSaveToClipboardTriggered(self, checked):
        mime = self.dockWidget.currentMime()
        self.centralWidget.setMime(mime, self.viewMode)

    def _onActionVisualTriggered(self, checked):
        self.viewMode = 0
        self._refresh()

    def _onActionRawDataTriggered(self, checked):
        self.viewMode = 1
        self._refresh()

    def _onActionHexViewTriggered(self, checked):
        self.viewMode = 2
        self._refresh()

    def _onMimeChanged(self, mime):
        self.centralWidget.showMime(mime, self.viewMode)

    def _refresh(self):
        mime = self.dockWidget.currentMime()
        if len(mime) > 0:
            self._onMimeChanged(mime)


def _gui_main(app):
    window = MyWindow()
    window.show()

    app.exec_()


def _cli_main(app, mime):
    clipboard = QApplication.clipboard()
    mimeData = clipboard.mimeData()
    widget = None

    if mime:
        if mimeData.hasFormat(mime):
            data = mimeData.data(mime)
            if sys.stdout.isatty():
                print(decode_data(data))
            else:
                sys.stdout.buffer.write(data)
        else:
            print("Invalid format: " + mime)
    else:
        for format in mimeData.formats():
            print(format)


def except_hook(etype, value, tb):
    sys.__excepthook__(etype, value, tb)


# ignore the noisy "Failed to register clipboard format"
def qt_msg_handler(msg_type, context, msg):
    pass


def main():
    sys.excepthook = except_hook

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--cli", action="store_true",
                        help="command line mode")
    parser.add_argument("mime", nargs='?', help="show the mime content")
    args = parser.parse_args()

    qInstallMessageHandler(qt_msg_handler)

    app = QApplication(sys.argv)

    if args.cli:
        _cli_main(app, args.mime)
    else:
        _gui_main(app)

    # cleaup tmp dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

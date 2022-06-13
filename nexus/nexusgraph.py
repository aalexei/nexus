##
## Copyright 2010-2022 Alexei Gilchrist
##
## This file is part of Nexus.
##
## Nexus is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Nexus is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Nexus.  If not, see <http://www.gnu.org/licenses/>.


from . import graphydb, config, graphics, devonthink
import logging, re, base64, hashlib, os, json
import bleach
from bleach.linkifier import Linker
import urllib.parse
from urllib.request import urlopen


from PyQt5 import QtCore, QtGui

CONFIG = config.get_config()

def DataToImage(dataenc):
    '''
    Return an Image from encoded data
    '''
    image = QtGui.QImage()
    try:
        datadec = base64.b64decode(dataenc.encode('utf-8'))
        image.loadFromData(datadec)
    except Exception as e:
        logging.error('unable to load image data: "%s"', str(e))

    return image

def ImageToData(image):
    '''
    Return an encoded string of image data
    '''
    qbytearray = QtCore.QByteArray()
    buf = QtCore.QBuffer(qbytearray)
    image.save(buf,"PNG")

    dataenc = base64.b64encode(bytes(qbytearray)).decode('utf-8')

    return dataenc

##----------------------------------------------------------------------
class NexusGraph(graphydb.Graph):
    '''
    Adding some convenience functions on top of Graph specialised to Nexus
    '''

    # def findTag(self, tag):
    #     '''
    #     Tags should be unique by name
    #     '''
    #     tagnode = self.fetch('(n:Tag)','n.data.text=:tag', tag=tag).one
    #     return tagnode

    def findImageData(self, sha1):
        '''
        ImageData nodes should have unique sha1
        '''
        idnode = self.fetch('(n:ImageData)','n.data.sha1=:sha1', sha1=sha1).one
        return idnode

    def copyTrees(self, basenodes, batch=None, setchange=False):
        '''
        Recursively copy nodes to graph following out-edges from basenodes.
          basenodes: NSet of the base pf trees to copy
          find_resources: use existing ImageData nodes if present

        Return: copied basenodes
        '''

        nodes = graphydb.NSet(basenodes)
        basenodesuids = basenodes.get('uid')
        edges = graphydb.ESet()
        ns = nodes
        # Grab all the edges and nodes downstream (out)
        for ii in range(1000):
            # exclude any edges we have already looked at
            # (in case multiple selections includes children)
            es = ns.outE() - edges
            if len(es)==0:
                break
            ns = es.end
            edges |= es
            nodes |= ns
        else:
            logging.warn("Copy depth exceeded")

        D = {}
        nodes2 = graphydb.NSet()
        basenodes2 = graphydb.NSet()
        edges2 = graphydb.ESet()

        # copy nodes and assign new uids
        for n in nodes:
            found = False
            # if find_resources and n['kind'] == 'Tag':
            #     nt = self.findTag(n['text'])
            #     if nt is not None:
            #         D[n['uid']] = nt['uid']
            #         found = True

            if n['kind'] in ['ImageData']:
                nt = self.findImageData(n['sha1'])
                if nt is not None:
                    D[n['uid']] = nt['uid']
                    found = True

            if not found:
                n2 = n.copy(newuid=True)
                n2.setGraph(self)
                nodes2.add(n2)
                D[n['uid']] = n2['uid']
                if n['uid'] in basenodesuids:
                    basenodes2.add(n2)

        # re-link everything with new uids
        # potentially change graphs too
        for e in edges:
            e2 = e.copy(newuid=True)
            e2.setGraph(self)
            e2['startuid'] = D[e2['startuid']]
            e2['enduid'] = D[e2['enduid']]
            edges2.add(e2)

        nodes2.save(setchange=setchange, batch=batch)
        edges2.save(setchange=setchange, batch=batch)

        return basenodes2

    def deleteOutFromNodes(self, nodes, batch=None, setchange=False):
        '''
        Delete nodes and any connected by out edges
        '''
        if len(nodes)==0:
            return
        children = nodes.outN()
        for n in nodes:
            if n['kind'] in ['ImageData'] and n.inE(COUNT=True)>0:
                # Don't delete data nodes with remaining links
                continue
            n.delete(disconnect=True, batch=batch, setchange=setchange)
        self.deleteOutFromNodes(children, batch=batch, setchange=setchange)

    def getCopyNode(self, clear=False):

        # Clear contents of CopyNode
        copynode = self.fetch('(n:CopyNode)').one
        if copynode is None:
            copynode = self.Node('CopyNode')
            copynode.save(setchange=False)

        if clear:
            self.deleteOutFromNodes(copynode.outN())

        return copynode

    def getNodeLink(self, node=None):

        # form url to CopyNode
        mappath = self.path

        if node is not None:
            uid = node['uid']
            link = 'nexus:{}#{}'.format(mappath, uid)
        else:
            link = 'nexus:{}'.format(mappath)

        return link

    def getNodeFromLink(self, link):

        so = re.search('nexus:([^#]+)#(.+)\s*', link)
        if not so:
            return (None, "Unable to get nexus item link from data")
        mappath = so.group(1)
        nodeuid = so.group(2)

        g = NexusGraph(mappath)
        node = g.getuid(nodeuid)
        if node is None:
            return (None, "Node no longer exists in source")

        # if node.graph.getsetting('version') != self.getsetting('version'):
        #     return (None, "pasted graph version does not match current version %s"%str(VERSION))

        return (node, "Success")

    def copyNodeWithMimedata(self, mimedata):
        '''
        Add stems from mimedata to CopyNode
        '''
        # print('formats:', mimedata.formats())
        # print('text:', mimedata.text())
        # print('urls:', mimedata.urls())
        # print(mimedata.html())

        # What about multiple formats present?
        logging.debug(f"mimedata available: {mimedata.formats()}")
        if mimedata.hasUrls():
            logging.debug(f"mimedata ulrs: {mimedata.urls()}")
        if mimedata.hasHtml():
            logging.debug(f"mimedata html: {mimedata.html()}")
        if mimedata.hasText():
            logging.debug(f"mimedata html: {mimedata.text()}")


        if mimedata.hasFormat('application/x-nexus'):
            data = mimedata.data('application/x-nexus')
            nexuslink = bytes(data).decode('utf-8')
            copynode, msg = self.getNodeFromLink(nexuslink)

        if mimedata.hasFormat('application/json'):
            rawdata = mimedata.data('application/json')
            data = json.loads(bytes(rawdata))
            copynode, msg = self.itemFromJSON(data)

        elif mimedata.hasImage():
            imagedata = mimedata.imageData()
            copynode, msg = self.itemFromImage(imagedata)

        elif mimedata.hasHtml():
            html = mimedata.html()
            copynode, msg = self.itemFromHtml(html)

        elif mimedata.hasUrls():
            urls = mimedata.urls()
            copynode, msg = self.itemFromUrls(urls)

        elif mimedata.hasText():
            text = mimedata.text()
            copynode, msg = self.itemFromText(text)

        return copynode, msg

    def itemFromJSON(self, data):

        dataenc = data['image']
        image = DataToImage(dataenc)

        # TODO combine with itemFromImage
        sha1 = hashlib.sha1(dataenc.encode('utf-8')).hexdigest()

        ## limit images to this size or scale down
        MAXSIZE = 1000

        scale = 1.0
        maxside = max( image.width(), image.height() )
        if maxside > MAXSIZE:
            scale = MAXSIZE/float(maxside)

        # heuristic, on retina screens need to scale down:
        scale = scale/4.0

        T = [scale, 0.0, 0.0, 0.0, scale, 0.0, 0.0, 0.0, 1.0]

        imgnode = self.Node('Image')
        imgnode['frame'] = T
        imgnode['z'] = 0
        imgnode['sha1'] = sha1
        imgnode.save(setchange=False)

        # TODO chack to see if data exists already
        datanode = self.Node('ImageData')
        datanode['data'] = dataenc
        datanode['sha1'] = sha1
        datanode.save(setchange=False)

        copynode = self.getCopyNode(clear=True)
        stem = self.Node('Stem', pos=[10,10], flip=1,
                         scale=0.6).save(setchange=False)

        self.Edge(copynode, 'Child', stem).save(setchange=False)
        self.Edge(stem, 'In', imgnode).save(setchange=False)
        self.Edge(imgnode, 'With', datanode).save(setchange=False)

        if 'citekey' in data:
            citekey=data['citekey']
            url=f'ook:{citekey}'
            if 'page' in data:
                page = data['page']
                url+=f'?page={page}'
            item =  self.Node('Text')
            item['maxwidth'] = CONFIG['text_item_width']
            item['source'] = f'<a href="{url}">[{citekey}]</a>'
            item['frame'] = graphics.Transform().tolist()
            item['z'] = 0
            item.save(setchange=False)

            stem2 = self.Node('Stem', pos=[10, 15], flip=-1,
                              scale=0.3).save(setchange=False)

            self.Edge(stem, 'Child', stem2).save(setchange=False)
            self.Edge(stem2, 'In', item).save(setchange=False)

        return copynode, "OK"

    def itemFromImage(self, image):
        # XXX image: jpg/png distinctions?

        dataenc = ImageToData(image)
        sha1 = hashlib.sha1(dataenc.encode('utf-8')).hexdigest()

        ## limit images to this size or scale down
        MAXSIZE = 1000

        scale = 1.0
        maxside = max( image.width(), image.height() )
        if maxside > MAXSIZE:
            scale = MAXSIZE/float(maxside)

        # heuristic, on retina screens need to scale down:
        scale = scale/4.0

        T = [scale, 0.0, 0.0, 0.0, scale, 0.0, 0.0, 0.0, 1.0]

        imgnode = self.Node('Image')
        imgnode['frame'] = T
        imgnode['z'] = 0
        imgnode['sha1'] = sha1
        imgnode.save(setchange=False)

        # TODO chack to see if data exists already
        datanode = self.Node('ImageData')
        datanode['data'] = dataenc
        datanode['sha1'] = sha1
        datanode.save(setchange=False)

        copynode = self.getCopyNode(clear=True)
        stem = self.Node('Stem', pos=[10,10], flip=1,
                         scale=0.6).save(setchange=False)

        self.Edge(copynode, 'Child', stem).save(setchange=False)
        self.Edge(stem, 'In', imgnode).save(setchange=False)
        self.Edge(imgnode, 'With', datanode).save(setchange=False)

        return copynode, "OK"

    def itemFromUrls(self, urls):

        copynode = self.getCopyNode(clear=True)
        for url in urls:
            bits=urllib.parse.urlparse(url.toString())

            if bits.scheme=='file':
                path = bits.path

                ## check to see if the url points to an image
                reader = QtGui.QImageReader(path)
                if reader.canRead():
                    image = reader.read()
                    return self.itemFromImage(image)

                else:
                    ## transfrom path into a relative path

                    mappath = str(self.path)
                    if len(os.path.dirname(mappath))==0:
                        ## file not saved yet, keep path unchanged
                        filepath = path
                    else:
                        ## make path relative to map
                        filepath = os.path.relpath(bits.path, os.path.dirname(mappath))

                    name = os.path.basename(bits.path)
                    if name == '':
                        pathbits = bits.path.split("/")
                        name = pathbits[-2]

                    logging.debug('mappath: %s filepath: %s path: %s',mappath, filepath, path)

                    text = '<a href="%s">%s</a>'%(filepath, name)

            else:
                path = url.toString()
                bits = path.split("/")
                if len(bits[-1])>0:
                    name = bits[-1]
                else:
                    name = path

                if str(url.scheme())=='x-devonthink-item':
                    ## fix for DT - links are uppercase and casesensitive
                    ## but QT lowercases the host part!
                    linkpath = str(url.host()).upper()
                    info = devonthink.getInfo(linkpath)
                    query = url.query()
                    if len(query)>0:
                        linkpath += "?" + query
                    text = '<a href="x-devonthink-item:%s">%s</a>'%(linkpath, info['name'])


                elif str(url.scheme())=='bookends':
                    uuid = str(url.path())[1:]
                    data = devonthink.getBEinfo(uuid)

                    authors = []
                    for a in data.get('authors','').split('\n'):
                        ns = a.split(',')
                        if len(ns)>0:
                            authors.append(ns[0])
                    authors = ' '.join(authors)
                    title = data.get('title','???')
                    so = re.match('(1\d\d\d|2\d\d\d)', data.get('thedate','????'))
                    if so:
                        year = so.group()
                    else:
                        year = '????'
                    journal = data.get('journal','')
                    if len(journal)>0:
                        journal = '<br/><i>'+journal+'</i>'

                    text = '<b>{year}</b> {authors}<br/><a href="{link}">{title}</a> {journal}'.format(
                        link = url.toString(),
                        title=title,
                        authors=authors,
                        year=year,
                        journal=journal,
                    )

                else:
                    text = '<a href="%s">%s</a>'%(url.toString(), name)

            item =  self.Node('Text')
            item['maxwidth'] = CONFIG['text_item_width'] 
            item['source'] = text
            item['frame'] = graphics.Transform().tolist()
            item['z'] = 0
            item.save(setchange=False)

            stem = self.Node('Stem', pos=[10,10], flip=1,
                             scale=0.6).save(setchange=False)

            self.Edge(copynode, 'Child', stem).save(setchange=False)
            self.Edge(stem, 'In', item).save(setchange=False)

        return copynode, 'OK'


    def itemFromHtml(self, html):
        ## sanitise the input
        html = bleach.clean(html, strip=True,
                            protocols = bleach.ALLOWED_PROTOCOLS+['papers3', 'omnifocus', 'zotero']
                            )

        item = self.Node('Text')
        item['maxwidth'] = CONFIG['text_item_width']
        item['source'] = html
        item['frame'] = graphics.Transform().tolist()
        item['z'] = 0
        item.save(setchange=False)

        copynode = self.getCopyNode(clear=True)
        stem = self.Node('Stem', pos=[10,10], flip=1, z=0, scale=0.6).save(setchange=False)

        self.Edge(copynode, 'Child', stem).save(setchange=False)
        self.Edge(stem, 'In', item).save(setchange=False)

        return copynode, "OK"


    def itemFromText(self, text):
        #if text.startswith('papers3://'):
        #    ## this is actually an application url
        #    text = '<a href="%s">papers3</a>'%text
        #elif text.startswith('omnifocus://'):
        #    text = '<a href="%s">omnifocus</a>'%text
        #else:
        #
        #    # XXX Genaralise the url linker below to include papers3 and omnifocus?
        #
        #    text=re.sub("((http[s]?|file)://(?:[a-zA-Z]|[0-9]|[#$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)",  r'<a href="\1">\1</a>', text)
#
        #    # XXX <pre> doesn't work so well .. maybe "paste as"
        #    ## check to see if text has \n or \r and wrap in <pre> </pre> tags
        #    if re.search(r'\\n|\\r',text):
        #        #text = "<code>%s</code>"%text
        #        text = re.sub(r"\\n|\\r", r"<br />\\n", text)
        #
        #    text = text.strip()

        # first linkify any perculiar protocols
        link_re = re.compile(
            r"""({0}):[//]?[\w\-\/_]+""".format(
                '|'.join(['papers3', 'omnifocus', 'zotero'])
            ), re.IGNORECASE | re.VERBOSE | re.UNICODE)
        linker = Linker(url_re = link_re)
        html = linker.linkify(text)

        # handle ook links
        def processook(match):
            citekey = match.group(1)
            with urlopen(f"http://localhost:9999/api?cmd=details&citekey={citekey}") as response:
                raw = response.read()
            data = json.loads(raw)
            ref = f'<table bgcolor="#f0f0ff" cellpadding="5"><tr><td>' \
                f'<a href="ook:{citekey}">{data["title"]}</a><hr/>' \
                f'<p style="font-size:8pt;margin-top:0px;margin-bottom:0px;qq">{data["names"]} <i>{data["ref"]}</i></p>' \
                f'</td></tr></table>'
            return ref
        html = re.sub(r'ook:(\w+)', processook, html, re.DOTALL)

        # now linkify any other urls
        html = bleach.linkify(html)

        item = self.Node('Text')
        item['maxwidth'] = CONFIG['text_item_width']
        item['source'] = html
        item['frame'] = graphics.Transform().tolist()
        item['z'] = 0
        item.save(setchange=False)

        copynode = self.getCopyNode(clear=True)
        stem = self.Node('Stem', pos=[10,10], flip=1, z=0, scale=0.6).save(setchange=False)

        self.Edge(copynode, 'Child', stem).save(setchange=False)
        self.Edge(stem, 'In', item).save(setchange=False)

        return copynode, "OK"

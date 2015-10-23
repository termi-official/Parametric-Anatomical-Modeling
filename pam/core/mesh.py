import numpy
#import scipy.spatial.distance

class Mesh():

    def __init__(self, polygons, name = ''):
        self.polygons = numpy.array(polygons)
        self.uv_quadtree = Quadtree.buildUVQuadtreeFromMesh(self.polygons)
        self.octree = Octree.buildOctree(self.polygons)
        self.polygon_transformation_cache = [None] * len(self.polygons)
        self.name = name

    def findClosestPointOnMesh(self, point):
        # Find closest node
        nodes = self.octree.listNodes()
        p = numpy.array(point)
        closest_node = nodes[0]
        node_distance = distance_sqr(p, nodes[0].center)
        for n in nodes:
            d = distance_sqr(p, n.center)
            if d < node_distance:
                closest_node = n
                node_distance = d
        polygons = closest_node.getPolygonsUpwards()
        node_distance_extended = numpy.square(numpy.sqrt(node_distance) + numpy.sqrt(distance_sqr(numpy.array((closest_node.bounds[0], closest_node.bounds[2], closest_node.bounds[4])), closest_node.center)))
        for n in nodes:
            if distance_sqr(p, n.center) < node_distance_extended:
                polygons.extend(n.getPolygonsUpwards())
        polygons = numpy.unique(polygons)
        closest_distance = numpy.inf
        closest_point = None
        for poly_index in polygons:
            triangle_point, _ = self._cachedClosestPointOnTriangle(point, poly_index)
            d = distance_sqr(triangle_point, point)
            if d < closest_distance:
                closest_distance = d
                polygon_index = poly_index
                closest_point = triangle_point
        print(len(polygons), '/', len(self.polygons), "polygons checked")
        return closest_point, polygon_index

    def _cachedClosestPointOnTriangle(self, point, polygon_index):
        # http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.104.4264&rep=rep1&type=pdf

        t1 = self.polygons[polygon_index][0][:3]
        t2 = self.polygons[polygon_index][1][:3]
        t3 = self.polygons[polygon_index][2][:3]

        if self.polygon_transformation_cache[polygon_index] is not None:
            # Get Transformation if cached
            mat = self.polygon_transformation_cache[polygon_index]
        else:
            # Else generate new and cache it
            mat = calculatePlaneTransformation(t1, t2, t3)
            self.polygon_transformation_cache[polygon_index] = mat

        # Apply to points
        p1 = multiply_4d_matrix(mat, t1)[1:3]
        p2 = multiply_4d_matrix(mat, t2)[1:3]
        p3 = multiply_4d_matrix(mat, t3)[1:3]

        point_transform = multiply_4d_matrix(mat, point)
        plane_distance = point_transform[0]
        point_plane = point_transform[1:3]

        polygon_point = getClosestPointOnPolygon2d(point_plane, p1, p2, p3)
        l1, l2, l3 = toBarycentricCoordinates(polygon_point, p1, p2, p3)

        point_3d = fromBarycentricCoordinates(l1, l2, l3, t1, t2, t3)
        return point_3d, (l1, l2, l3)

    def raycast(self, origin, direction):
        # TODO octree optimization, only check polys that are inside hit cubes
        closest_poly_index = None
        closest_distance_sqr = numpy.inf
        closest_intersection = None
        for i, poly in enumerate(self.polygons):
            intersection = intersectRayTri(origin, direction, poly[0][:3], poly[1][:3], poly[2][:3])
            if intersection is not None:
                d = distance_sqr(intersection, origin)
                if d < closest_distance_sqr:
                    closest_distance_sqr = d
                    closest_poly_index = i
                    closest_intersection = intersection

        if closest_poly_index is not None:
            return closest_intersection, closest_poly_index, numpy.sqrt(closest_distance_sqr)
        else:
            return None

class Octree():
    """[INSERT DOCSTRING HERE]
    bounds: [-x, +x, -y, +y, -z, +z] 

    bot       top
    +---+---+ +---+---+
    | 2 | 3 | | 6 | 7 |
    +---+---+ +---+---+ ^
    | 0 | 1 | | 4 | 5 | y
    +---+---+ +---+---+ +-x->
    
    """
    def __init__(self, bounds, polygon_reference, parent = None, max_depth = 4):
        self.nodes = [None] * 8
        self.bounds = bounds
        self.polygons = []
        self.max_depth = max_depth
        self.parent = parent
        self.polygon_reference = polygon_reference
        self.center = numpy.array(((self.bounds[0] + self.bounds[1]) / 2,
                       (self.bounds[2] + self.bounds[3]) / 2,
                       (self.bounds[4] + self.bounds[5]) / 2))

    def addPolygon(self, polygon_index):
        if self.max_depth > 0:
            for i in range(8):
                sb = self._getSubtreeBounds(i)
                if polygonInBounds(self.polygon_reference[polygon_index][...,:3], sb):
                    if self.nodes[i] is None:
                        self.nodes[i] = Octree(sb, self.polygon_reference, self, self.max_depth - 1)
                    self.nodes[i].addPolygon(polygon_index)
                    return
        self.polygons.append(polygon_index)

    def getPolygonIndices(self, point):
        if not pointInBounds(point, self.bounds):
            return []
        else:
            result = list(self.polygons)
            for node in self.nodes:
                if node is not None:
                    result.extend(node.getPolygonIndices(point))
            return result

    def _getSubtreeBounds(self, index):
        b = self.bounds
        x = (b[0] + b[1]) / 2
        y = (b[2] + b[3]) / 2
        z = (b[4] + b[5]) / 2
        if index == 0:
            sb = [b[0], x, b[2], y, b[4], z]
        elif index == 1:
            sb = [x, b[1], b[2], y, b[4], z]
        elif index == 2:
            sb = [b[0], x, y, b[3], b[4], z]
        elif index == 3:
            sb = [x, b[1], y, b[3], b[4], z]
        elif index == 4:
            sb = [b[0], x, b[2], y, z, b[5]]
        elif index == 5:
            sb = [x, b[1], b[2], y, z, b[5]]
        elif index == 6:
            sb = [b[0], x, y, b[3], z, b[5]]
        elif index == 7:
            sb = [x, b[1], y, b[3], z, b[5]]
        else:
            raise ValueError("Only indices from [0..7] allowed")
        return sb

    def listNodes(self):
        l = [self]
        for node in self.nodes:
            if node is not None:
                l.extend(node.listNodes())
        return l

    def getPolygonsUpwards(self):
        if self.parent is not None:
            l = list(self.polygons)
            l.extend(self.parent.getPolygonsUpwards())
            return l
        else:
            return self.polygons

    @staticmethod
    def buildOctree(polygons):
        # Find bounds of all polygons
        b = [polygons[0][0][0], polygons[0][0][0], polygons[0][0][1], polygons[0][0][1], polygons[0][0][2], polygons[0][0][2]]
        for poly in polygons:
            for p in poly:
                b[0] = min(b[0], p[0])
                b[1] = max(b[1], p[0])
                b[2] = min(b[2], p[1])
                b[3] = max(b[3], p[1])
                b[4] = min(b[4], p[2])
                b[5] = max(b[5], p[2])

        octree = Octree(b, polygons)
        for poly_index in range(len(polygons)):
            octree.addPolygon(poly_index)
        return octree
"""Quadtrees for caching uv-maps"""

# Dict with cached uv-maps
quadtrees = {}

class Quadtree:
    """Represents a node in the quadtree in which Polygons can be inserted.
    A Polygon is a tuple of two lists of the same size. The first list contains the
    uv-coordinates and the second the 3d-coordinates. Only the uv-coordinates are used
    for sorting into the quadtree, the rest is just for storage."""
    def __init__(self, left, top, right, bottom):
        """Left, top, right, bottom are the boundaries of this quad"""
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
        self.children = [None, None, None, None]
        self.polygons = []

    def addPolygon(self, polygon):
        """Inserts a polygon into the quadtree."""
        if self.children[0]:
            if self.children[0].addPolygon(polygon):
                return True
            if self.children[1].addPolygon(polygon):
                return True
            if self.children[2].addPolygon(polygon):
                return True
            if self.children[3].addPolygon(polygon):
                return True
        for p in polygon[...,3:]:
            if p[0] < self.left or p[0] > self.right or p[1] < self.top or p[1] > self.bottom:
                return False
        self.polygons.append(polygon)
        return True

    def getPolygons(self, point):
        """Gives a list of all polygons in the quadtree that may contain the point"""
        p = point
        if p[0] < self.left or p[0] > self.right or p[1] < self.top or p[1] > self.bottom:
            return []
        else:
            result = list(self.polygons)
            if all(self.children):
                result.extend(self.children[0].getPolygons(p))
                result.extend(self.children[1].getPolygons(p))
                result.extend(self.children[2].getPolygons(p))
                result.extend(self.children[3].getPolygons(p))
            return result

    @staticmethod
    def buildQuadtree(depth = 2, left = 0.0, top = 0.0, right = 1.0, bottom = 1.0):
        """Builds a new quadtree recursively with the given depth."""
        node = Quadtree(left, top, right, bottom)
        if depth > 0:
            v = (top + bottom) / 2
            h = (left + right) / 2
            node.children[0] = Quadtree.buildQuadtree(depth - 1, left, top, h, v)
            node.children[1] = Quadtree.buildQuadtree(depth - 1, h, top, right, v)
            node.children[2] = Quadtree.buildQuadtree(depth - 1, left, v, h, bottom)
            node.children[3] = Quadtree.buildQuadtree(depth - 1, h, v, right, bottom)
        return node

    @staticmethod
    def buildUVQuadtreeFromMesh(polygons, depth = 2):
        left  = 0.0
        right = 1.0
        top = 0.0
        bot = 1.0

        for uvs in polygons[...,3:]:
            for uv in uvs:
                left = min(left, uv[0])
                right = max(right, uv[0])
                top = min(top, uv[1])
                bot = max(bot, uv[1])
        qtree = Quadtree.buildQuadtree(depth, left = left, right = right, top = top, bottom = bot)
        for polygon in polygons:
            qtree.addPolygon(polygon)
        return qtree

def polygonInBounds(polygon, bounds):
    for p in polygon:
        if not pointInBounds(p, bounds):
            return False
    return True

def pointInBounds(point, bounds):
    if point[0] < bounds[0] \
    or point[0] > bounds[1] \
    or point[1] < bounds[2] \
    or point[1] > bounds[3] \
    or point[2] < bounds[4] \
    or point[2] > bounds[5]:
        return False
    return True

def closestPointOnTriangle(point, t1, t2, t3):
    # http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.104.4264&rep=rep1&type=pdf

    # Get Transformation
    mat = calculatePlaneTransformation(t1, t2, t3)

    # Apply to points
    p1 = multiply_4d_matrix(mat, t1)[1:3]
    p2 = multiply_4d_matrix(mat, t2)[1:3]
    p3 = multiply_4d_matrix(mat, t3)[1:3]

    point_transform = multiply_4d_matrix(mat, point)
    plane_distance = point_transform[0]
    point_plane = point_transform[1:3]

    polygon_point = getClosestPointOnPolygon2d(point_plane, p1, p2, p3)
    l1, l2, l3 = toBarycentricCoordinates(polygon_point, p1, p2, p3)

    point_3d = fromBarycentricCoordinates(l1, l2, l3, t1, t2, t3)
    return point_3d, (l1, l2, l3)

def getClosestPointOnPolygon2d(point, p1, p2, p3):
    p1p2 = edge_distance(point, p1, p2)
    p2p3 = edge_distance(point, p2, p3)
    p3p1 = edge_distance(point, p3, p1)
    if p1p2 >= 0 and p2p3 >= 0 and p3p1 >= 0:
        return numpy.array(point)
    p1p2_p = _edge_distance_perpendicular(point, p1, p2)
    p2p1_p = _edge_distance_perpendicular(point, p2, p1)
    p2p3_p = _edge_distance_perpendicular(point, p2, p3)
    p3p2_p = _edge_distance_perpendicular(point, p3, p2)
    p3p1_p = _edge_distance_perpendicular(point, p3, p1)
    p1p3_p = _edge_distance_perpendicular(point, p1, p3)

    if p1p2 < 0 and p1p2_p < 0 and p2p1_p < 0:
        return getClosestPointOnLine(point, p1, p2)
    elif p2p3 < 0 and p2p3_p < 0 and p3p2_p < 0:
        return getClosestPointOnLine(point, p2, p3)
    elif p3p1 < 0 and p3p1_p < 0 and p1p3_p < 0:
        return getClosestPointOnLine(point, p3, p1)
    elif p1p2_p > 0 and p1p3_p > 0:
        return numpy.array(p1)
    elif p2p3_p > 0 and p2p1_p > 0:
        return numpy.array(p2)
    elif p3p1_p > 0 and p3p2_p > 0:
        return numpy.array(p3)
    return None

def intersectPointTri2d(point, p1, p2, p3):
    p1p2 = edge_distance(point, p1, p2)
    p2p3 = edge_distance(point, p2, p3)
    p3p1 = edge_distance(point, p3, p1)
    if p1p2 >= 0 and p2p3 >= 0 and p3p1 >= 0:
        return True
    else:
        return False

def intersectRayTri(p, v, t1, t2, t3):
    mat = getRotationMatrix(v)
    print(t1, t2, t3, p, mat, '---\n')
    p1 = numpy.dot(mat, t1)[1:3]
    p2 = numpy.dot(mat, t2)[1:3]
    p3 = numpy.dot(mat, t3)[1:3]
    p = numpy.dot(mat, p)[1:3]
    print(p1, p2, p3, p, p1.shape)
    if intersectPointTri2d(p, p1, p2, p3):
        l1, l2, l3 = toBarycentricCoordinates(p, p1, p2, p3)
        print(l1, l2, l3, t1, t2, t3)
        return fromBarycentricCoordinates(l1, l2, l3, t1, t2, t3)
    return None

def getClosestPointOnLine(point, p1, p2):
    p1_point = point - p1
    p1_p2 = p2 - p1
    p1_p2_dist2 = p1_p2[0]**2 + p1_p2[1]**2

    dot = numpy.dot(p1_point, p1_p2)

    t = dot / p1_p2_dist2

    return numpy.array((p1[0] + p1_p2[0] * t, p1[1] + p1_p2[1] * t))

def edge_distance(point, l1, l2):
    return (point[0] - l1[0]) * (l2[1] - l1[1]) - (point[1] - l1[1]) * (l2[0] - l1[0])

def _edge_distance_perpendicular(point, l1, l2):
    return (point[0] - l1[0]) * (l1[0] - l2[0]) - (point[1] - l1[1]) * (l2[1] - l1[1])

def multiply_4d_matrix(mat, vec):
    v = numpy.array((0.,0.,0.,1.), dtype=numpy.float32)
    v[0:len(vec)] = vec
    v = numpy.dot(mat, v)
    v /= v[3]
    return v[:3]

def calculatePlaneTransformation(t1, t2, t3):
    # Translation of p1 to origin
    translation_matrix = numpy.identity(4)
    translation_matrix[0][-1] = -t1[0]
    translation_matrix[1][-1] = -t1[1]
    translation_matrix[2][-1] = -t1[2]

    # Rotation of normal to point to x-axis
    # http://math.stackexchange.com/questions/180418/calculate-rotation-matrix-to-align-vector-a-to-vector-b-in-3d
    # TODO: Optimize for 0-values
    a = numpy.cross(t3 - t1, t2 - t1)
    r = getRotationMatrix(a)
    rotation_matrix = numpy.identity(4)
    rotation_matrix[0:3, 0:3] = r

    mat = numpy.dot(rotation_matrix, translation_matrix)
    return mat

def getRotationMatrix(vector):
    a = numpy.array(vector, dtype=numpy.float32)
    a /= numpy.linalg.norm(vector)
    b = numpy.array((1,0,0))
    v = numpy.cross(a, b)
    v_len_2 = numpy.dot(v,v)
    if v_len_2 == 0:
        return numpy.identity(3)
    c = numpy.dot(a, b)
    vx = numpy.array([[0, -v[2], v[1]],[v[2], 0, -v[0]],[-v[1], v[0], 0]])
    r = numpy.identity(3) + vx + numpy.dot(vx,vx) * ((1-c)/(v_len_2))
    return r

def toBarycentricCoordinates(point, t1, t2, t3):
    det = ((t2[1] - t3[1]) * (t1[0] - t3[0]) + (t3[0] - t2[0]) * (t1[1] - t3[1]))
    l1 = ((t2[1] - t3[1]) * (point[0] - t3[0]) + (t3[0] - t2[0]) * (point[1] - t3[1])) / det
    l2 = ((t3[1] - t1[1]) * (point[0] - t3[0]) + (t1[0] - t3[0]) * (point[1] - t3[1])) / det
    l3 = 1 - l1 - l2
    return (l1, l2, l3)

def fromBarycentricCoordinates(l1, l2, l3, t1, t2, t3):
    return l1 * t1 + l2 * t2 + l3 * t3

def distance_sqr(p1, p2):
    p = p2 - p1
    return numpy.dot(p, p)

def map3dPointToUV(mesh, point):
    """Convert a given 3d-point into uv-coordinates

    :param mesh: The source 3d-mesh on which to project the point before mapping
    :type mesh: Mesh
    :param point: The 3d point which to project onto uv
    :type point: numpy.array (should be 3d)

    :return: The transformed point in uv-space
    :rtype: numpy.array (2d)
    """

    p, f = mesh.findClosestPointOnMesh(point)

    # get the uv-coordinate of the first triangle of the polygon
    A = mesh.polygons[f][0][:3]
    B = mesh.polygons[f][1][:3]
    C = mesh.polygons[f][2][:3]

    # and the uv-coordinates of the first triangle
    uvs = mesh.polygons[f][...,3:]
    U = uvs[0]
    V = uvs[1]
    W = uvs[2]

    # convert 3d-coordinates of point p to uv-coordinates
    _, (l1, l2, l3) = mesh._cachedClosestPointOnTriangle(point, f)
    p_uv = fromBarycentricCoordinates(l1, l2, l3, U, V, W)

    p_uv_2d = p_uv[:2]

    return numpy.array(p_uv_2d)

def mapUVPointTo3d(mesh, uv_list, cleanup=True):
    """Convert a list of uv-points into 3d. 
    This function is mostly used by interpolateUVTrackIn3D. Note, that 
    therefore, not all points can and have to be converted to 3d points. 
    The return list can therefore have less points than the uv-list. 
    This cleanup can be deactivated by setting cleanup = False. Then, 
    the return-list may contain some [] elements.

    This function makes use of a quadtree cache managed in pam.model.

    :param mesh: The mesh with the uv-map
    :type mesh: Mesh
    :param uv_list: The list of uv-coordinates to convert
    :type uv_list: List of numpy.array (arrays should be 2d)
    :param cleanup: If set to False, unmapped uv-coordinates are 
        removed from the return list
    :type cleanup: bool

    :return: List of converted 3d-points
    :rtype: list of numpy.array or []
    """

    uv_list_range_container = range(len(uv_list))

    points_3d = [[] for _ in uv_list_range_container]
    point_indices = [i for i in uv_list_range_container]

    # Get uv-quadtree from mesh
    qtree = mesh.uv_quadtree

    for i in point_indices:
        point = uv_list[i]
        polygons = qtree.getPolygons(point)
        for polygon in polygons:
            uvs = polygon[...,3:]
            p3ds = polygon[...,:3]
            result = intersectPointTri2d(
                point,
                uvs[0],
                uvs[2],
                uvs[1]
            )

            if (result):
                l1, l2, l3 = toBarycentricCoordinates(point, uvs[0], uvs[1], uvs[2])
                points_3d[i] = fromBarycentricCoordinates(l1, l2, l3, p3ds[0], p3ds[1], p3ds[2])
                break

    if cleanup:
        points_3d = [p for p in points_3d if len(p) > 0]

    return points_3d

def map3dPointTo3d(mesh1, mesh2, point, normal=None):
    """Map a 3d-point on a given object on another object. Both objects must have the
    same topology. The closest point on the mesh of the first object is projected onto 
    the mesh of the second object.

    :param o1: The source object
    :type o1: bpy.types.Object
    :param o2: The target object
    :type o2: bpy.types.Object
    :param point: The point to transform
    :type point: mathutils.Vector
    :param normal: If a normal is given, the point on the target mesh is not determined 
        by the closest point on the mesh, but by raycast along the normal
    :type normal: mathutils.Vector

    :return: The transformed point
    :rtype: mathutils.Vector
    """

    # if normal is None, we don't worry about orthogonal projections
    if normal is None:
        # get point, normal and face of closest point to a given point
        p, n, f = o1.closest_point_on_mesh(point)
    else:
        p, n, f = o1.ray_cast(point + normal * constants.RAY_FAC, point - normal * constants.RAY_FAC)
        # if no collision could be detected, return None
        if f == -1:
            return None

    # if o1 and o2 are identical, there is nothing more to do
    if (o1 == o2):
        return p

    # get the vertices of the first triangle of the polygon from both objects
    A1 = o1.data.vertices[o1.data.polygons[f].vertices[0]].co
    B1 = o1.data.vertices[o1.data.polygons[f].vertices[1]].co
    C1 = o1.data.vertices[o1.data.polygons[f].vertices[2]].co

    # project the point on a 2d-surface and check, whether we are in the right triangle
    t1 = mathutils.Vector()
    t2 = mathutils.Vector((1.0, 0.0, 0.0))
    t3 = mathutils.Vector((0.0, 1.0, 0.0))

    p_test = mathutils.geometry.barycentric_transform(p, A1, B1, C1, t1, t2, t3)

    # if the point is on the 2d-triangle, proceed with the real barycentric_transform
    if mathutils.geometry.intersect_point_tri_2d(p_test.to_2d(), t1.xy, t2.xy, t3.xy) == 1:
        A2 = o2.data.vertices[o2.data.polygons[f].vertices[0]].co
        B2 = o2.data.vertices[o2.data.polygons[f].vertices[1]].co
        C2 = o2.data.vertices[o2.data.polygons[f].vertices[2]].co

        # convert 3d-coordinates of the point
        p_new = mathutils.geometry.barycentric_transform(p, A1, B1, C1, A2, B2, C2)

    else:
        # use the other triangle
        A1 = o1.data.vertices[o1.data.polygons[f].vertices[0]].co
        B1 = o1.data.vertices[o1.data.polygons[f].vertices[2]].co
        C1 = o1.data.vertices[o1.data.polygons[f].vertices[3]].co

        A2 = o2.data.vertices[o2.data.polygons[f].vertices[0]].co
        B2 = o2.data.vertices[o2.data.polygons[f].vertices[2]].co
        C2 = o2.data.vertices[o2.data.polygons[f].vertices[3]].co

        # convert 3d-coordinates of the point
        p_new = mathutils.geometry.barycentric_transform(p, A1, B1, C1, A2, B2, C2)

    return p_new

def test():
    # Testing
    p = [[(1.1749176979064941, 4.809549331665039, 1.7694251537322998, 1.9868213740892315e-08, 0.6666667461395264), (1.1749176979064941, 2.809549331665039, 1.7694251537322998, 0.333333283662796, 0.6666667461395264), (-0.8250824213027954, 2.809549570083618, 1.7694251537322998, 0.3333333134651184, 1.0)], [(-0.8250822424888611, 4.809549331665039, 3.7694251537323, 0.666666567325592, 0.6666667461395264), (-0.8250826597213745, 2.8095498085021973, 3.7694251537323, 0.3333333432674408, 0.6666666865348816), (1.1749169826507568, 2.809548854827881, 3.7694251537323, 0.3333333134651184, 0.33333349227905273)], [(1.1749181747436523, 4.809548854827881, 3.7694251537323, 0.33333340287208557, 0.3333333134651184), (1.1749169826507568, 2.809548854827881, 3.7694251537323, 0.3333333134651184, 0.0), (1.1749176979064941, 2.809549331665039, 1.7694251537322998, 0.6666666269302368, 1.9868211964535476e-08)], [(1.1749169826507568, 2.809548854827881, 3.7694251537323, 0.0, 1.291433733285885e-07), (-0.8250826597213745, 2.8095498085021973, 3.7694251537323, 0.33333322405815125, 0.0), (-0.8250824213027954, 2.809549570083618, 1.7694251537322998, 0.3333333134651184, 0.33333325386047363)], [(-0.8250826597213745, 2.8095498085021973, 3.7694251537323, 0.6666667461395264, 0.3333333134651184), (-0.8250822424888611, 4.809549331665039, 3.7694251537323, 0.6666666865348816, 8.940695295223122e-08), (-0.8250819444656372, 4.809549808502197, 1.7694251537322998, 1.0, 0.0)], [(1.1749176979064941, 4.809549331665039, 1.7694251537322998, 0.333333283662796, 0.33333343267440796), (-0.8250819444656372, 4.809549808502197, 1.7694251537322998, 0.3333333134651184, 0.6666666269302368), (-0.8250822424888611, 4.809549331665039, 3.7694251537323, 2.9802320611338473e-08, 0.6666667461395264)], [(1.1434125900268555, -0.10950565338134766, 1.744723916053772, 0.333333283662796, 0.6666667461395264), (-0.8565876483917236, -0.10950541496276855, 1.744723916053772, 0.3333333134651184, 1.0), (-0.8565871715545654, 1.890494704246521, 1.744723916053772, 0.0, 1.0)], [(-0.8565874099731445, 1.8904943466186523, 3.7447237968444824, 0.666666567325592, 0.6666667461395264), (-0.8565878868103027, -0.10950517654418945, 3.7447237968444824, 0.3333333432674408, 0.6666666865348816), (1.1434118747711182, -0.10950613021850586, 3.7447237968444824, 0.3333333134651184, 0.33333349227905273)], [(1.1434130668640137, 1.8904938697814941, 3.7447237968444824, 0.33333340287208557, 0.3333333134651184), (1.1434118747711182, -0.10950613021850586, 3.7447237968444824, 0.3333333134651184, 0.0), (1.1434125900268555, -0.10950565338134766, 1.744723916053772, 0.6666666269302368, 1.9868211964535476e-08)], [(1.1434118747711182, -0.10950613021850586, 3.7447237968444824, 0.0, 1.291433733285885e-07), (-0.8565878868103027, -0.10950517654418945, 3.7447237968444824, 0.33333322405815125, 0.0), (-0.8565876483917236, -0.10950541496276855, 1.744723916053772, 0.3333333134651184, 0.33333325386047363)], [(-0.8565878868103027, -0.10950517654418945, 3.7447237968444824, 0.6666667461395264, 0.3333333134651184), (-0.8565874099731445, 1.8904943466186523, 3.7447237968444824, 0.6666666865348816, 8.940695295223122e-08), (-0.8565871715545654, 1.890494704246521, 1.744723916053772, 1.0, 0.0)], [(1.1434125900268555, 1.8904943466186523, 1.744723916053772, 0.333333283662796, 0.33333343267440796), (-0.8565871715545654, 1.890494704246521, 1.744723916053772, 0.3333333134651184, 0.6666666269302368), (-0.8565874099731445, 1.8904943466186523, 3.7447237968444824, 2.9802320611338473e-08, 0.6666667461395264)], [(1.1434125900268555, -0.10950565338134766, -0.4854733943939209, 0.333333283662796, 0.6666667461395264), (-0.8565876483917236, -0.10950541496276855, -0.4854733943939209, 0.3333333134651184, 1.0), (-0.8565871715545654, 1.890494704246521, -0.4854733943939209, 0.0, 1.0)], [(-0.8565874099731445, 1.8904943466186523, 1.5145264863967896, 0.666666567325592, 0.6666667461395264), (-0.8565878868103027, -0.10950517654418945, 1.5145264863967896, 0.3333333432674408, 0.6666666865348816), (1.1434118747711182, -0.10950613021850586, 1.5145264863967896, 0.3333333134651184, 0.33333349227905273)], [(1.1434130668640137, 1.8904938697814941, 1.5145264863967896, 0.33333340287208557, 0.3333333134651184), (1.1434118747711182, -0.10950613021850586, 1.5145264863967896, 0.3333333134651184, 0.0), (1.1434125900268555, -0.10950565338134766, -0.4854733943939209, 0.6666666269302368, 1.9868211964535476e-08)], [(1.1434118747711182, -0.10950613021850586, 1.5145264863967896, 0.0, 1.291433733285885e-07), (-0.8565878868103027, -0.10950517654418945, 1.5145264863967896, 0.33333322405815125, 0.0), (-0.8565876483917236, -0.10950541496276855, -0.4854733943939209, 0.3333333134651184, 0.33333325386047363)], [(-0.8565878868103027, -0.10950517654418945, 1.5145264863967896, 0.6666667461395264, 0.3333333134651184), (-0.8565874099731445, 1.8904943466186523, 1.5145264863967896, 0.6666666865348816, 8.940695295223122e-08), (-0.8565871715545654, 1.890494704246521, -0.4854733943939209, 1.0, 0.0)], [(1.1434125900268555, 1.8904943466186523, -0.4854733943939209, 0.333333283662796, 0.33333343267440796), (-0.8565871715545654, 1.890494704246521, -0.4854733943939209, 0.3333333134651184, 0.6666666269302368), (-0.8565874099731445, 1.8904943466186523, 1.5145264863967896, 2.9802320611338473e-08, 0.6666667461395264)], [(1.1434125900268555, 2.8110692501068115, -0.4854733943939209, 0.333333283662796, 0.6666667461395264), (-0.8565876483917236, 2.8110694885253906, -0.4854733943939209, 0.3333333134651184, 1.0), (-0.8565871715545654, 4.811069488525391, -0.4854733943939209, 0.0, 1.0)], [(1.1434130668640137, 4.811068534851074, 1.5145264863967896, 0.6666666269302368, 0.33333340287208557), (-0.8565874099731445, 4.811069488525391, 1.5145264863967896, 0.666666567325592, 0.6666667461395264), (-0.8565878868103027, 2.8110697269439697, 1.5145264863967896, 0.3333333432674408, 0.6666666865348816)], [(1.1434130668640137, 4.811068534851074, 1.5145264863967896, 0.33333340287208557, 0.3333333134651184), (1.1434118747711182, 2.8110687732696533, 1.5145264863967896, 0.3333333134651184, 0.0), (1.1434125900268555, 2.8110692501068115, -0.4854733943939209, 0.6666666269302368, 1.9868211964535476e-08)], [(1.1434118747711182, 2.8110687732696533, 1.5145264863967896, 0.0, 1.291433733285885e-07), (-0.8565878868103027, 2.8110697269439697, 1.5145264863967896, 0.33333322405815125, 0.0), (-0.8565876483917236, 2.8110694885253906, -0.4854733943939209, 0.3333333134651184, 0.33333325386047363)], [(-0.8565878868103027, 2.8110697269439697, 1.5145264863967896, 0.6666667461395264, 0.3333333134651184), (-0.8565874099731445, 4.811069488525391, 1.5145264863967896, 0.6666666865348816, 8.940695295223122e-08), (-0.8565871715545654, 4.811069488525391, -0.4854733943939209, 1.0, 0.0)], [(1.1434125900268555, 4.811069488525391, -0.4854733943939209, 0.333333283662796, 0.33333343267440796), (-0.8565871715545654, 4.811069488525391, -0.4854733943939209, 0.3333333134651184, 0.6666666269302368), (-0.8565874099731445, 4.811069488525391, 1.5145264863967896, 2.9802320611338473e-08, 0.6666667461395264)], [(3.6120681762695312, 2.8110692501068115, -0.4854733943939209, 0.333333283662796, 0.6666667461395264), (1.6120679378509521, 2.8110694885253906, -0.4854733943939209, 0.3333333134651184, 1.0), (1.6120684146881104, 4.811069488525391, -0.4854733943939209, 0.0, 1.0)], [(3.6120686531066895, 4.811068534851074, 1.5145264863967896, 0.6666666269302368, 0.33333340287208557), (1.6120681762695312, 4.811069488525391, 1.5145264863967896, 0.666666567325592, 0.6666667461395264), (1.612067699432373, 2.8110697269439697, 1.5145264863967896, 0.3333333432674408, 0.6666666865348816)], [(3.6120686531066895, 4.811068534851074, 1.5145264863967896, 0.33333340287208557, 0.3333333134651184), (3.612067461013794, 2.8110687732696533, 1.5145264863967896, 0.3333333134651184, 0.0), (3.6120681762695312, 2.8110692501068115, -0.4854733943939209, 0.6666666269302368, 1.9868211964535476e-08)], [(3.612067461013794, 2.8110687732696533, 1.5145264863967896, 0.0, 1.291433733285885e-07), (1.612067699432373, 2.8110697269439697, 1.5145264863967896, 0.33333322405815125, 0.0), (1.6120679378509521, 2.8110694885253906, -0.4854733943939209, 0.3333333134651184, 0.33333325386047363)], [(1.612067699432373, 2.8110697269439697, 1.5145264863967896, 0.6666667461395264, 0.3333333134651184), (1.6120681762695312, 4.811069488525391, 1.5145264863967896, 0.6666666865348816, 8.940695295223122e-08), (1.6120684146881104, 4.811069488525391, -0.4854733943939209, 1.0, 0.0)], [(3.6120681762695312, 4.811069488525391, -0.4854733943939209, 0.333333283662796, 0.33333343267440796), (1.6120684146881104, 4.811069488525391, -0.4854733943939209, 0.3333333134651184, 0.6666666269302368), (1.6120681762695312, 4.811069488525391, 1.5145264863967896, 2.9802320611338473e-08, 0.6666667461395264)], [(3.6120681762695312, -0.10272097587585449, -0.4854733943939209, 0.333333283662796, 0.6666667461395264), (1.6120679378509521, -0.10272073745727539, -0.4854733943939209, 0.3333333134651184, 1.0), (1.6120684146881104, 1.8972793817520142, -0.4854733943939209, 0.0, 1.0)], [(1.6120681762695312, 1.8972790241241455, 1.5145264863967896, 0.666666567325592, 0.6666667461395264), (1.612067699432373, -0.10272049903869629, 1.5145264863967896, 0.3333333432674408, 0.6666666865348816), (3.612067461013794, -0.1027214527130127, 1.5145264863967896, 0.3333333134651184, 0.33333349227905273)], [(3.6120686531066895, 1.8972785472869873, 1.5145264863967896, 0.33333340287208557, 0.3333333134651184), (3.612067461013794, -0.1027214527130127, 1.5145264863967896, 0.3333333134651184, 0.0), (3.6120681762695312, -0.10272097587585449, -0.4854733943939209, 0.6666666269302368, 1.9868211964535476e-08)], [(3.612067461013794, -0.1027214527130127, 1.5145264863967896, 0.0, 1.291433733285885e-07), (1.612067699432373, -0.10272049903869629, 1.5145264863967896, 0.33333322405815125, 0.0), (1.6120679378509521, -0.10272073745727539, -0.4854733943939209, 0.3333333134651184, 0.33333325386047363)], [(1.612067699432373, -0.10272049903869629, 1.5145264863967896, 0.6666667461395264, 0.3333333134651184), (1.6120681762695312, 1.8972790241241455, 1.5145264863967896, 0.6666666865348816, 8.940695295223122e-08), (1.6120684146881104, 1.8972793817520142, -0.4854733943939209, 1.0, 0.0)], [(3.6120681762695312, 1.8972790241241455, -0.4854733943939209, 0.333333283662796, 0.33333343267440796), (1.6120684146881104, 1.8972793817520142, -0.4854733943939209, 0.3333333134651184, 0.6666666269302368), (1.6120681762695312, 1.8972790241241455, 1.5145264863967896, 2.9802320611338473e-08, 0.6666667461395264)], [(3.6120681762695312, -0.10272097587585449, 1.7943341732025146, 0.333333283662796, 0.6666667461395264), (1.6120679378509521, -0.10272073745727539, 1.7943341732025146, 0.3333333134651184, 1.0), (1.6120684146881104, 1.8972793817520142, 1.7943341732025146, 0.0, 1.0)], [(1.6120681762695312, 1.8972790241241455, 3.7943339347839355, 0.666666567325592, 0.6666667461395264), (1.612067699432373, -0.10272049903869629, 3.7943339347839355, 0.3333333432674408, 0.6666666865348816), (3.612067461013794, -0.1027214527130127, 3.7943339347839355, 0.3333333134651184, 0.33333349227905273)], [(3.6120686531066895, 1.8972785472869873, 3.7943339347839355, 0.33333340287208557, 0.3333333134651184), (3.612067461013794, -0.1027214527130127, 3.7943339347839355, 0.3333333134651184, 0.0), (3.6120681762695312, -0.10272097587585449, 1.7943341732025146, 0.6666666269302368, 1.9868211964535476e-08)], [(3.612067461013794, -0.1027214527130127, 3.7943339347839355, 0.0, 1.291433733285885e-07), (1.612067699432373, -0.10272049903869629, 3.7943339347839355, 0.33333322405815125, 0.0), (1.6120679378509521, -0.10272073745727539, 1.7943341732025146, 0.3333333134651184, 0.33333325386047363)], [(1.612067699432373, -0.10272049903869629, 3.7943339347839355, 0.6666667461395264, 0.3333333134651184), (1.6120681762695312, 1.8972790241241455, 3.7943339347839355, 0.6666666865348816, 8.940695295223122e-08), (1.6120684146881104, 1.8972793817520142, 1.7943341732025146, 1.0, 0.0)], [(3.6120681762695312, 1.8972790241241455, 1.7943341732025146, 0.333333283662796, 0.33333343267440796), (1.6120684146881104, 1.8972793817520142, 1.7943341732025146, 0.3333333134651184, 0.6666666269302368), (1.6120681762695312, 1.8972790241241455, 3.7943339347839355, 2.9802320611338473e-08, 0.6666667461395264)], [(-0.8250819444656372, 4.809549808502197, 1.7694251537322998, 0.0, 1.0), (1.1749176979064941, 4.809549331665039, 1.7694251537322998, 1.9868213740892315e-08, 0.6666667461395264), (-0.8250824213027954, 2.809549570083618, 1.7694251537322998, 0.3333333134651184, 1.0)], [(1.1749181747436523, 4.809548854827881, 3.7694251537323, 0.6666666269302368, 0.33333340287208557), (-0.8250822424888611, 4.809549331665039, 3.7694251537323, 0.666666567325592, 0.6666667461395264), (1.1749169826507568, 2.809548854827881, 3.7694251537323, 0.3333333134651184, 0.33333349227905273)], [(1.1749176979064941, 4.809549331665039, 1.7694251537322998, 0.6666666865348816, 0.333333283662796), (1.1749181747436523, 4.809548854827881, 3.7694251537323, 0.33333340287208557, 0.3333333134651184), (1.1749176979064941, 2.809549331665039, 1.7694251537322998, 0.6666666269302368, 1.9868211964535476e-08)], [(1.1749176979064941, 2.809549331665039, 1.7694251537322998, 2.9802320611338473e-08, 0.33333340287208557), (1.1749169826507568, 2.809548854827881, 3.7694251537323, 0.0, 1.291433733285885e-07), (-0.8250824213027954, 2.809549570083618, 1.7694251537322998, 0.3333333134651184, 0.33333325386047363)], [(-0.8250824213027954, 2.809549570083618, 1.7694251537322998, 1.0, 0.3333333134651184), (-0.8250826597213745, 2.8095498085021973, 3.7694251537323, 0.6666667461395264, 0.3333333134651184), (-0.8250819444656372, 4.809549808502197, 1.7694251537322998, 1.0, 0.0)], [(1.1749181747436523, 4.809548854827881, 3.7694251537323, 0.0, 0.33333340287208557), (1.1749176979064941, 4.809549331665039, 1.7694251537322998, 0.333333283662796, 0.33333343267440796), (-0.8250822424888611, 4.809549331665039, 3.7694251537323, 2.9802320611338473e-08, 0.6666667461395264)], [(1.1434125900268555, 1.8904943466186523, 1.744723916053772, 1.9868213740892315e-08, 0.6666667461395264), (1.1434125900268555, -0.10950565338134766, 1.744723916053772, 0.333333283662796, 0.6666667461395264), (-0.8565871715545654, 1.890494704246521, 1.744723916053772, 0.0, 1.0)], [(1.1434130668640137, 1.8904938697814941, 3.7447237968444824, 0.6666666269302368, 0.33333340287208557), (-0.8565874099731445, 1.8904943466186523, 3.7447237968444824, 0.666666567325592, 0.6666667461395264), (1.1434118747711182, -0.10950613021850586, 3.7447237968444824, 0.3333333134651184, 0.33333349227905273)], [(1.1434125900268555, 1.8904943466186523, 1.744723916053772, 0.6666666865348816, 0.333333283662796), (1.1434130668640137, 1.8904938697814941, 3.7447237968444824, 0.33333340287208557, 0.3333333134651184), (1.1434125900268555, -0.10950565338134766, 1.744723916053772, 0.6666666269302368, 1.9868211964535476e-08)], [(1.1434125900268555, -0.10950565338134766, 1.744723916053772, 2.9802320611338473e-08, 0.33333340287208557), (1.1434118747711182, -0.10950613021850586, 3.7447237968444824, 0.0, 1.291433733285885e-07), (-0.8565876483917236, -0.10950541496276855, 1.744723916053772, 0.3333333134651184, 0.33333325386047363)], [(-0.8565876483917236, -0.10950541496276855, 1.744723916053772, 1.0, 0.3333333134651184), (-0.8565878868103027, -0.10950517654418945, 3.7447237968444824, 0.6666667461395264, 0.3333333134651184), (-0.8565871715545654, 1.890494704246521, 1.744723916053772, 1.0, 0.0)], [(1.1434130668640137, 1.8904938697814941, 3.7447237968444824, 0.0, 0.33333340287208557), (1.1434125900268555, 1.8904943466186523, 1.744723916053772, 0.333333283662796, 0.33333343267440796), (-0.8565874099731445, 1.8904943466186523, 3.7447237968444824, 2.9802320611338473e-08, 0.6666667461395264)], [(1.1434125900268555, 1.8904943466186523, -0.4854733943939209, 1.9868213740892315e-08, 0.6666667461395264), (1.1434125900268555, -0.10950565338134766, -0.4854733943939209, 0.333333283662796, 0.6666667461395264), (-0.8565871715545654, 1.890494704246521, -0.4854733943939209, 0.0, 1.0)], [(1.1434130668640137, 1.8904938697814941, 1.5145264863967896, 0.6666666269302368, 0.33333340287208557), (-0.8565874099731445, 1.8904943466186523, 1.5145264863967896, 0.666666567325592, 0.6666667461395264), (1.1434118747711182, -0.10950613021850586, 1.5145264863967896, 0.3333333134651184, 0.33333349227905273)], [(1.1434125900268555, 1.8904943466186523, -0.4854733943939209, 0.6666666865348816, 0.333333283662796), (1.1434130668640137, 1.8904938697814941, 1.5145264863967896, 0.33333340287208557, 0.3333333134651184), (1.1434125900268555, -0.10950565338134766, -0.4854733943939209, 0.6666666269302368, 1.9868211964535476e-08)], [(1.1434125900268555, -0.10950565338134766, -0.4854733943939209, 2.9802320611338473e-08, 0.33333340287208557), (1.1434118747711182, -0.10950613021850586, 1.5145264863967896, 0.0, 1.291433733285885e-07), (-0.8565876483917236, -0.10950541496276855, -0.4854733943939209, 0.3333333134651184, 0.33333325386047363)], [(-0.8565876483917236, -0.10950541496276855, -0.4854733943939209, 1.0, 0.3333333134651184), (-0.8565878868103027, -0.10950517654418945, 1.5145264863967896, 0.6666667461395264, 0.3333333134651184), (-0.8565871715545654, 1.890494704246521, -0.4854733943939209, 1.0, 0.0)], [(1.1434130668640137, 1.8904938697814941, 1.5145264863967896, 0.0, 0.33333340287208557), (1.1434125900268555, 1.8904943466186523, -0.4854733943939209, 0.333333283662796, 0.33333343267440796), (-0.8565874099731445, 1.8904943466186523, 1.5145264863967896, 2.9802320611338473e-08, 0.6666667461395264)], [(1.1434125900268555, 4.811069488525391, -0.4854733943939209, 1.9868213740892315e-08, 0.6666667461395264), (1.1434125900268555, 2.8110692501068115, -0.4854733943939209, 0.333333283662796, 0.6666667461395264), (-0.8565871715545654, 4.811069488525391, -0.4854733943939209, 0.0, 1.0)], [(1.1434118747711182, 2.8110687732696533, 1.5145264863967896, 0.3333333134651184, 0.33333349227905273), (1.1434130668640137, 4.811068534851074, 1.5145264863967896, 0.6666666269302368, 0.33333340287208557), (-0.8565878868103027, 2.8110697269439697, 1.5145264863967896, 0.3333333432674408, 0.6666666865348816)], [(1.1434125900268555, 4.811069488525391, -0.4854733943939209, 0.6666666865348816, 0.333333283662796), (1.1434130668640137, 4.811068534851074, 1.5145264863967896, 0.33333340287208557, 0.3333333134651184), (1.1434125900268555, 2.8110692501068115, -0.4854733943939209, 0.6666666269302368, 1.9868211964535476e-08)], [(1.1434125900268555, 2.8110692501068115, -0.4854733943939209, 2.9802320611338473e-08, 0.33333340287208557), (1.1434118747711182, 2.8110687732696533, 1.5145264863967896, 0.0, 1.291433733285885e-07), (-0.8565876483917236, 2.8110694885253906, -0.4854733943939209, 0.3333333134651184, 0.33333325386047363)], [(-0.8565876483917236, 2.8110694885253906, -0.4854733943939209, 1.0, 0.3333333134651184), (-0.8565878868103027, 2.8110697269439697, 1.5145264863967896, 0.6666667461395264, 0.3333333134651184), (-0.8565871715545654, 4.811069488525391, -0.4854733943939209, 1.0, 0.0)], [(1.1434130668640137, 4.811068534851074, 1.5145264863967896, 0.0, 0.33333340287208557), (1.1434125900268555, 4.811069488525391, -0.4854733943939209, 0.333333283662796, 0.33333343267440796), (-0.8565874099731445, 4.811069488525391, 1.5145264863967896, 2.9802320611338473e-08, 0.6666667461395264)], [(3.6120681762695312, 4.811069488525391, -0.4854733943939209, 1.9868213740892315e-08, 0.6666667461395264), (3.6120681762695312, 2.8110692501068115, -0.4854733943939209, 0.333333283662796, 0.6666667461395264), (1.6120684146881104, 4.811069488525391, -0.4854733943939209, 0.0, 1.0)], [(3.612067461013794, 2.8110687732696533, 1.5145264863967896, 0.3333333134651184, 0.33333349227905273), (3.6120686531066895, 4.811068534851074, 1.5145264863967896, 0.6666666269302368, 0.33333340287208557), (1.612067699432373, 2.8110697269439697, 1.5145264863967896, 0.3333333432674408, 0.6666666865348816)], [(3.6120681762695312, 4.811069488525391, -0.4854733943939209, 0.6666666865348816, 0.333333283662796), (3.6120686531066895, 4.811068534851074, 1.5145264863967896, 0.33333340287208557, 0.3333333134651184), (3.6120681762695312, 2.8110692501068115, -0.4854733943939209, 0.6666666269302368, 1.9868211964535476e-08)], [(3.6120681762695312, 2.8110692501068115, -0.4854733943939209, 2.9802320611338473e-08, 0.33333340287208557), (3.612067461013794, 2.8110687732696533, 1.5145264863967896, 0.0, 1.291433733285885e-07), (1.6120679378509521, 2.8110694885253906, -0.4854733943939209, 0.3333333134651184, 0.33333325386047363)], [(1.6120679378509521, 2.8110694885253906, -0.4854733943939209, 1.0, 0.3333333134651184), (1.612067699432373, 2.8110697269439697, 1.5145264863967896, 0.6666667461395264, 0.3333333134651184), (1.6120684146881104, 4.811069488525391, -0.4854733943939209, 1.0, 0.0)], [(3.6120686531066895, 4.811068534851074, 1.5145264863967896, 0.0, 0.33333340287208557), (3.6120681762695312, 4.811069488525391, -0.4854733943939209, 0.333333283662796, 0.33333343267440796), (1.6120681762695312, 4.811069488525391, 1.5145264863967896, 2.9802320611338473e-08, 0.6666667461395264)], [(3.6120681762695312, 1.8972790241241455, -0.4854733943939209, 1.9868213740892315e-08, 0.6666667461395264), (3.6120681762695312, -0.10272097587585449, -0.4854733943939209, 0.333333283662796, 0.6666667461395264), (1.6120684146881104, 1.8972793817520142, -0.4854733943939209, 0.0, 1.0)], [(3.6120686531066895, 1.8972785472869873, 1.5145264863967896, 0.6666666269302368, 0.33333340287208557), (1.6120681762695312, 1.8972790241241455, 1.5145264863967896, 0.666666567325592, 0.6666667461395264), (3.612067461013794, -0.1027214527130127, 1.5145264863967896, 0.3333333134651184, 0.33333349227905273)], [(3.6120681762695312, 1.8972790241241455, -0.4854733943939209, 0.6666666865348816, 0.333333283662796), (3.6120686531066895, 1.8972785472869873, 1.5145264863967896, 0.33333340287208557, 0.3333333134651184), (3.6120681762695312, -0.10272097587585449, -0.4854733943939209, 0.6666666269302368, 1.9868211964535476e-08)], [(3.6120681762695312, -0.10272097587585449, -0.4854733943939209, 2.9802320611338473e-08, 0.33333340287208557), (3.612067461013794, -0.1027214527130127, 1.5145264863967896, 0.0, 1.291433733285885e-07), (1.6120679378509521, -0.10272073745727539, -0.4854733943939209, 0.3333333134651184, 0.33333325386047363)], [(1.6120679378509521, -0.10272073745727539, -0.4854733943939209, 1.0, 0.3333333134651184), (1.612067699432373, -0.10272049903869629, 1.5145264863967896, 0.6666667461395264, 0.3333333134651184), (1.6120684146881104, 1.8972793817520142, -0.4854733943939209, 1.0, 0.0)], [(3.6120686531066895, 1.8972785472869873, 1.5145264863967896, 0.0, 0.33333340287208557), (3.6120681762695312, 1.8972790241241455, -0.4854733943939209, 0.333333283662796, 0.33333343267440796), (1.6120681762695312, 1.8972790241241455, 1.5145264863967896, 2.9802320611338473e-08, 0.6666667461395264)], [(3.6120681762695312, 1.8972790241241455, 1.7943341732025146, 1.9868213740892315e-08, 0.6666667461395264), (3.6120681762695312, -0.10272097587585449, 1.7943341732025146, 0.333333283662796, 0.6666667461395264), (1.6120684146881104, 1.8972793817520142, 1.7943341732025146, 0.0, 1.0)], [(3.6120686531066895, 1.8972785472869873, 3.7943339347839355, 0.6666666269302368, 0.33333340287208557), (1.6120681762695312, 1.8972790241241455, 3.7943339347839355, 0.666666567325592, 0.6666667461395264), (3.612067461013794, -0.1027214527130127, 3.7943339347839355, 0.3333333134651184, 0.33333349227905273)], [(3.6120681762695312, 1.8972790241241455, 1.7943341732025146, 0.6666666865348816, 0.333333283662796), (3.6120686531066895, 1.8972785472869873, 3.7943339347839355, 0.33333340287208557, 0.3333333134651184), (3.6120681762695312, -0.10272097587585449, 1.7943341732025146, 0.6666666269302368, 1.9868211964535476e-08)], [(3.6120681762695312, -0.10272097587585449, 1.7943341732025146, 2.9802320611338473e-08, 0.33333340287208557), (3.612067461013794, -0.1027214527130127, 3.7943339347839355, 0.0, 1.291433733285885e-07), (1.6120679378509521, -0.10272073745727539, 1.7943341732025146, 0.3333333134651184, 0.33333325386047363)], [(1.6120679378509521, -0.10272073745727539, 1.7943341732025146, 1.0, 0.3333333134651184), (1.612067699432373, -0.10272049903869629, 3.7943339347839355, 0.6666667461395264, 0.3333333134651184), (1.6120684146881104, 1.8972793817520142, 1.7943341732025146, 1.0, 0.0)], [(3.6120686531066895, 1.8972785472869873, 3.7943339347839355, 0.0, 0.33333340287208557), (3.6120681762695312, 1.8972790241241455, 1.7943341732025146, 0.333333283662796, 0.33333343267440796), (1.6120681762695312, 1.8972790241241455, 3.7943339347839355, 2.9802320611338473e-08, 0.6666667461395264)]]
    m = Mesh(p)
    p1 = (2,2,3)
    p2 = numpy.array((3.208115816116333, 2.262561798095703, 2.304555892944336))
    p3 = numpy.array((2.2930221557617188, 0.4895104169845581, 4.062463760375977))
    # mat = calculatePlaneTransformation(p1, p2, p3)
    # a = numpy.dot(mat, numpy.array((p3[0], p3[1], p3[2], 1)).reshape(4,1))
    # a /= a[3]
    # print(mat, a, sep=('\n'))
    # m.findClosestPointOnMesh((-1,-1,-1))
    # print(closestPointOnTriangle((7,6,10), p1, p2, p3))
    p,_ = m.findClosestPointOnMesh((0,0,0))
    print(map3dPointToUV(m, p))
    print(mapUVPointTo3d(m, [numpy.array((0.01, 0.7))]))
    # import bpy
    # import mathutils
    # mat = calculatePlaneTransformation(p1, p2, p3)
    # bpy.context.active_object.matrix_world = mathutils.Matrix(mat)

def runtime_test():
    p1 = (2,2,3)
    p2 = numpy.array((3.208115816116333, 2.262561798095703, 2.304555892944336))
    p3 = numpy.array((2.2930221557617188, 0.4895104169845581, 4.062463760375977))
    for i in range(10000):
        closestPointOnTriangle((7,6,10), p1, p2, p3)

def blenderTest():
    import bpy
    import mathutils
    p1 = numpy.array((2,2,3))
    p2 = numpy.array((3.208115816116333, 2.262561798095703, 2.304555892944336))
    p3 = numpy.array((2.2930221557617188, 0.4895104169845581, 4.062463760375977))
    bpy.context.scene.cursor_location = mathutils.Vector(intersectRayTri(bpy.context.scene.cursor_location.to_tuple(), (1,1,1), p1, p2, p3))

# import cProfile
if __name__ == "__main__":
    test()
    # cProfile.run('runtime_test()')
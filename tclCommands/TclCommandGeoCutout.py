from tclCommands.TclCommand import TclCommandSignaled
from FlatCAMObj import FlatCAMGerber, FlatCAMGeometry

import logging
import collections
from copy import deepcopy
from shapely.ops import cascaded_union
from shapely.geometry import Polygon, LineString, LinearRing

log = logging.getLogger('base')


class TclCommandGeoCutout(TclCommandSignaled):
    """
        Tcl shell command to create a board cutout geometry.
        Allow cutout for any shape.
        Cuts holding gaps from geometry.

        example:

        """

    # List of all command aliases, to be able use old
    # names for backward compatibility (add_poly, add_polygon)
    aliases = ['geocutout', 'geoc']

    # Dictionary of types from Tcl command, needs to be ordered
    arg_names = collections.OrderedDict([
        ('name', str),
    ])

    # Dictionary of types from Tcl command, needs to be ordered,
    # this  is  for options  like -optionname value
    option_types = collections.OrderedDict([
        ('dia', float),
        ('margin', float),
        ('gapsize', float),
        ('gaps', str)
    ])

    # array of mandatory options for current Tcl command: required = {'name','outname'}
    required = ['name']

    # structured help for current command, args needs to be ordered
    help = {
        'main': 'Creates board cutout from an object (Gerber or Geometry) of any shape',
        'args': collections.OrderedDict([
            ('name', 'Name of the object.'),
            ('dia', 'Tool diameter.'),
            ('margin', 'Margin over bounds.'),
            ('gapsize', 'size of gap.'),
            ('gaps', "type of gaps. Can be: 'tb' = top-bottom, 'lr' = left-right, '2tb' = 2top-2bottom, "
                     "'2lr' = 2left-2right, '4' = 4 cuts, '8' = 8 cuts")
        ]),
        'examples': ["      #isolate margin for example from fritzing arduino shield or any svg etc\n" +
                     "      isolate BCu_margin -dia 3 -overlap 1\n" +
                     "\n" +
                     "      #create exteriors from isolated object\n" +
                     "      exteriors BCu_margin_iso -outname BCu_margin_iso_exterior\n" +
                     "\n" +
                     "      #delete isolated object if you dond need id anymore\n" +
                     "      delete BCu_margin_iso\n" +
                     "\n" +
                     "      #finally cut holding gaps\n" +
                     "      geocutout BCu_margin_iso_exterior -dia 3 -gapsize 0.6 -gaps 4\n"]
    }

    flat_geometry = []

    def execute(self, args, unnamed_args):
        """

        :param args:
        :param unnamed_args:
        :return:
        """

        # def subtract_rectangle(obj_, x0, y0, x1, y1):
        #     pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        #     obj_.subtract_polygon(pts)

        def substract_rectangle_geo(geo, x0, y0, x1, y1):
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

            def flatten(geometry=None, reset=True, pathonly=False):
                """
                Creates a list of non-iterable linear geometry objects.
                Polygons are expanded into its exterior and interiors if specified.

                Results are placed in flat_geometry

                :param geometry: Shapely type or list or list of list of such.
                :param reset: Clears the contents of self.flat_geometry.
                :param pathonly: Expands polygons into linear elements.
                """

                if reset:
                    self.flat_geometry = []

                # If iterable, expand recursively.
                try:
                    for geo_el in geometry:
                        if geo_el is not None:
                            flatten(geometry=geo_el,
                                    reset=False,
                                    pathonly=pathonly)

                # Not iterable, do the actual indexing and add.
                except TypeError:
                    if pathonly and type(geometry) == Polygon:
                        self.flat_geometry.append(geometry.exterior)
                        flatten(geometry=geometry.interiors,
                                reset=False,
                                pathonly=True)
                    else:
                        self.flat_geometry.append(geometry)

                return self.flat_geometry

            flat_geometry = flatten(geo, pathonly=True)

            polygon = Polygon(pts)
            toolgeo = cascaded_union(polygon)
            diffs = []
            for target in flat_geometry:
                if type(target) == LineString or type(target) == LinearRing:
                    diffs.append(target.difference(toolgeo))
                else:
                    log.warning("Not implemented.")
            return cascaded_union(diffs)

        if 'name' in args:
            name = args['name']
        else:
            self.app.inform.emit(
                "[WARNING]The name of the object for which cutout is done is missing. Add it and retry.")
            return

        if 'margin' in args:
            margin = args['margin']
        else:
            margin = 0.001

        if 'dia' in args:
            dia = args['dia']
        else:
            dia = 0.1

        if 'gaps' in args:
            gaps = args['gaps']
        else:
            gaps = 4

        if 'gapsize' in args:
            gapsize = args['gapsize']
        else:
            gapsize = 0.1

        # Get source object.
        try:
            cutout_obj = self.app.collection.get_by_name(str(name))
        except Exception as e:
            log.debug("TclCommandGeoCutout --> %s" % str(e))
            return "Could not retrieve object: %s" % name

        if 0 in {dia}:
            self.app.inform.emit("[WARNING]Tool Diameter is zero value. Change it to a positive real number.")
            return "Tool Diameter is zero value. Change it to a positive real number."

        if gaps not in ['lr', 'tb', '2lr', '2tb', '4', '8']:
            self.app.inform.emit("[WARNING]Gaps value can be only one of: 'lr', 'tb', '2lr', '2tb', 4 or 8. "
                                 "Fill in a correct value and retry. ")
            return

        # Get min and max data for each object as we just cut rectangles across X or Y
        xmin, ymin, xmax, ymax = cutout_obj.bounds()
        cutout_obj.options['xmin'] = xmin
        cutout_obj.options['ymin'] = ymin
        cutout_obj.options['xmax'] = xmax
        cutout_obj.options['ymax'] = ymax

        px = 0.5 * (xmin + xmax) + margin
        py = 0.5 * (ymin + ymax) + margin
        lenghtx = (xmax - xmin) + (margin * 2)
        lenghty = (ymax - ymin) + (margin * 2)

        gapsize = gapsize / 2 + (dia / 2)

        try:
            gaps_u = int(gaps)
        except ValueError:
            gaps_u = gaps

        if isinstance(cutout_obj, FlatCAMGeometry):
            # rename the obj name so it can be identified as cutout
            # cutout_obj.options["name"] += "_cutout"

            # if gaps_u == 8 or gaps_u == '2lr':
            #     subtract_rectangle(cutout_obj,
            #                        xmin - gapsize,  # botleft_x
            #                        py - gapsize + lenghty / 4,  # botleft_y
            #                        xmax + gapsize,  # topright_x
            #                        py + gapsize + lenghty / 4)  # topright_y
            #     subtract_rectangle(cutout_obj,
            #                        xmin - gapsize,
            #                        py - gapsize - lenghty / 4,
            #                        xmax + gapsize,
            #                        py + gapsize - lenghty / 4)
            #
            # if gaps_u == 8 or gaps_u == '2tb':
            #     subtract_rectangle(cutout_obj,
            #                        px - gapsize + lenghtx / 4,
            #                        ymin - gapsize,
            #                        px + gapsize + lenghtx / 4,
            #                        ymax + gapsize)
            #     subtract_rectangle(cutout_obj,
            #                        px - gapsize - lenghtx / 4,
            #                        ymin - gapsize,
            #                        px + gapsize - lenghtx / 4,
            #                        ymax + gapsize)
            #
            # if gaps_u == 4 or gaps_u == 'lr':
            #     subtract_rectangle(cutout_obj,
            #                        xmin - gapsize,
            #                        py - gapsize,
            #                        xmax + gapsize,
            #                        py + gapsize)
            #
            # if gaps_u == 4 or gaps_u == 'tb':
            #     subtract_rectangle(cutout_obj,
            #                        px - gapsize,
            #                        ymin - gapsize,
            #                        px + gapsize,
            #                        ymax + gapsize)

            def geo_init(geo_obj, app_obj):
                geo = deepcopy(cutout_obj.solid_geometry)

                if gaps_u == 8 or gaps_u == '2lr':
                    geo = substract_rectangle_geo(geo,
                                                  xmin - gapsize,  # botleft_x
                                                  py - gapsize + lenghty / 4,  # botleft_y
                                                  xmax + gapsize,  # topright_x
                                                  py + gapsize + lenghty / 4)  # topright_y
                    geo = substract_rectangle_geo(geo,
                                                  xmin - gapsize,
                                                  py - gapsize - lenghty / 4,
                                                  xmax + gapsize,
                                                  py + gapsize - lenghty / 4)

                if gaps_u == 8 or gaps_u == '2tb':
                    geo = substract_rectangle_geo(geo,
                                                  px - gapsize + lenghtx / 4,
                                                  ymin - gapsize,
                                                  px + gapsize + lenghtx / 4,
                                                  ymax + gapsize)
                    geo = substract_rectangle_geo(geo,
                                                  px - gapsize - lenghtx / 4,
                                                  ymin - gapsize,
                                                  px + gapsize - lenghtx / 4,
                                                  ymax + gapsize)

                if gaps_u == 4 or gaps_u == 'lr':
                    geo = substract_rectangle_geo(geo,
                                                  xmin - gapsize,
                                                  py - gapsize,
                                                  xmax + gapsize,
                                                  py + gapsize)

                if gaps_u == 4 or gaps_u == 'tb':
                    geo = substract_rectangle_geo(geo,
                                                  px - gapsize,
                                                  ymin - gapsize,
                                                  px + gapsize,
                                                  ymax + gapsize)
                geo_obj.solid_geometry = deepcopy(geo)
                geo_obj.options['xmin'] = cutout_obj.options['xmin']
                geo_obj.options['ymin'] = cutout_obj.options['ymin']
                geo_obj.options['xmax'] = cutout_obj.options['xmax']
                geo_obj.options['ymax'] = cutout_obj.options['ymax']

                app_obj.disable_plots(objects=[cutout_obj])

                app_obj.inform.emit("[success] Any-form Cutout operation finished.")

            outname = cutout_obj.options["name"] + "_cutout"
            self.app.new_object('geometry', outname, geo_init, plot=False)

            # cutout_obj.plot()
            # self.app.inform.emit("[success] Any-form Cutout operation finished.")
            # self.app.plots_updated.emit()
        elif isinstance(cutout_obj, FlatCAMGerber):

            def geo_init(geo_obj, app_obj):
                try:
                    geo = cutout_obj.isolation_geometry((dia / 2), iso_type=0, corner=2, follow=None)
                except Exception as exc:
                    log.debug("TclCommandGeoCutout.execute() --> %s" % str(exc))
                    return 'fail'

                if gaps_u == 8 or gaps_u == '2lr':
                    geo = substract_rectangle_geo(geo,
                                                  xmin - gapsize,  # botleft_x
                                                  py - gapsize + lenghty / 4,  # botleft_y
                                                  xmax + gapsize,  # topright_x
                                                  py + gapsize + lenghty / 4)  # topright_y
                    geo = substract_rectangle_geo(geo,
                                                  xmin - gapsize,
                                                  py - gapsize - lenghty / 4,
                                                  xmax + gapsize,
                                                  py + gapsize - lenghty / 4)

                if gaps_u == 8 or gaps_u == '2tb':
                    geo = substract_rectangle_geo(geo,
                                                  px - gapsize + lenghtx / 4,
                                                  ymin - gapsize,
                                                  px + gapsize + lenghtx / 4,
                                                  ymax + gapsize)
                    geo = substract_rectangle_geo(geo,
                                                  px - gapsize - lenghtx / 4,
                                                  ymin - gapsize,
                                                  px + gapsize - lenghtx / 4,
                                                  ymax + gapsize)

                if gaps_u == 4 or gaps_u == 'lr':
                    geo = substract_rectangle_geo(geo,
                                                  xmin - gapsize,
                                                  py - gapsize,
                                                  xmax + gapsize,
                                                  py + gapsize)

                if gaps_u == 4 or gaps_u == 'tb':
                    geo = substract_rectangle_geo(geo,
                                                  px - gapsize,
                                                  ymin - gapsize,
                                                  px + gapsize,
                                                  ymax + gapsize)
                geo_obj.solid_geometry = deepcopy(geo)
                geo_obj.options['xmin'] = cutout_obj.options['xmin']
                geo_obj.options['ymin'] = cutout_obj.options['ymin']
                geo_obj.options['xmax'] = cutout_obj.options['xmax']
                geo_obj.options['ymax'] = cutout_obj.options['ymax']
                app_obj.inform.emit("[success] Any-form Cutout operation finished.")

            outname = cutout_obj.options["name"] + "_cutout"
            self.app.new_object('geometry', outname, geo_init, plot=False)

            cutout_obj = self.app.collection.get_by_name(outname)
        else:
            self.app.inform.emit("[ERROR]Cancelled. Object type is not supported.")
            return

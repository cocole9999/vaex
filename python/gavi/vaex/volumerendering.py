# -*- coding: utf-8 -*-
from qt import *

try:
	from PyQt4 import QtGui, QtCore
	from PyQt4 import QtOpenGL
except ImportError:
	from PySide import QtGui, QtCore
	from PySide import QtOpenGL
import OpenGL
from OpenGL.GL import * # import GL
from OpenGL.GL.framebufferobjects import *
from OpenGL.GLU import *
from OpenGL.GL.ARB.depth_texture import *
from OpenGL.GL.ARB.shadow import *
from OpenGL.GL import shaders

import numpy as np

import time

#import gavi.dataset
import gavi.vaex.colormaps
#print GL_R32F
GL_R32F = 33326	

class VolumeRenderWidget(QtOpenGL.QGLWidget):
	def __init__(self, parent = None, function_count=3):
		super(VolumeRenderWidget, self).__init__(parent)
		self.mouse_button_down = False
		self.mouse_button_down_right = False
		self.mouse_x, self.mouse_y = 0, 0
		self.angle1 = 0
		self.angle2 = 0
		self.mod1 = 0
		self.mod2 = 0
		self.mod3 = 0
		self.mod4 = 0
		self.mod5 = 0
		self.mod6 = 0
		
		self.orbit_angle = 0
		self.orbit_delay = 50
		self.orbiting = False
		
		self.function_count = function_count
		self.function_opacities = [0.1/2**(function_count-1-k) for k in range(function_count)] 
		self.function_sigmas = [0.05] * function_count
		self.function_means = (np.arange(function_count) / float(function_count-1)) * 0.8 + 0.10
		
		self.brightness = 5.
		self.min_level = 0.
		self.max_level = 1.

		self.min_level_vector3d = 0.
		self.max_level_vector3d = 1.
		self.texture_function_size = 1024*8


		self.texture_cube, self.texture_gradient = None, None
		self.setMouseTracking(True)
		shortcut = QtGui.QShortcut(QtGui.QKeySequence("space"), self)
		shortcut.activated.connect(self.toggle)
		self.texture_index = 1
		self.colormap_index = 0
		self.texture_size = 800 #*8
		self.grid = None
		# gets executed after initializeGL, can hook up your loading of data here
		self.post_init = lambda: 1
		
		self.arrow_model = Arrow(0, 0, 0, 4.)
		
	def orbit_start(self):
		self.orbiting = True
		self.orbit_time_previous = time.time()
		self.orbit_angle = 0
		self.update()
		QtCore.QTimer.singleShot(self.orbit_delay, self.orbit_progress)
		
	def orbit_stop(self):
		self.orbiting = False
		
	def orbit_progress(self):
		orbit_time_now = time.time()
		delta_time = orbit_time_now - self.orbit_time_previous
		if self.orbiting:
			self.orbit_angle += delta_time/4. * 360
			QtCore.QTimer.singleShot(self.orbit_delay, self.orbit_progress)
		else:
			self.orbit_angle = 0
		self.update()
		self.orbit_time_previous = orbit_time_now
		
	def toggle(self, ignore=None):
		print "toggle"
		self.texture_index += 1
		self.update()
		
	def create_shader_color(self):
		self.vertex_shader_color = shaders.compileShader("""
			varying vec4 vertex_color;
			void main() {
				gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
				vertex_color =  gl_Vertex /80. + vec4(0.5, 0.5, 0.5, 0.);
			}""",GL_VERTEX_SHADER)
		self.fragment_shader_color = shaders.compileShader("""
			varying vec4 vertex_color;
			void main() {
				gl_FragColor = vertex_color;
			}""",GL_FRAGMENT_SHADER)
		return shaders.compileProgram(self.vertex_shader_color, self.fragment_shader_color)

	def create_shader(self):
		

		self.vertex_shader = shaders.compileShader("""
			varying vec4 vertex_color;
			void main() {
				gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
				//vertex_color = gl_Color;
				vertex_color =  gl_Vertex.x > 1.5 ? vec4(1,0,0,0) : vec4(0,1,0,0)  ;// vec4(gl_Color) + vec4(1, 0, 0, 0);
				vertex_color =  gl_Vertex /80. + vec4(0.5, 0.5, 0.5, 0.);
			}""",GL_VERTEX_SHADER)
		self.fragment_shader = shaders.compileShader("""
			varying vec4 vertex_color;
			uniform sampler1D texture_colormap; 
			uniform sampler2D texture; 
			uniform sampler3D cube; 
			uniform sampler3D gradient;
			uniform vec2 size; // size of screen/fbo, to convert between pixels and uniform
			uniform vec2 minmax2d;
			uniform vec2 minmax3d;
			uniform vec2 minmax3d_total;
			//uniform float maxvalue2d;
			//uniform float maxvalue3d;
			uniform float alpha_mod; // mod3
			uniform float mod4;  // mafnifier
			uniform float mod5; // blend color and line integral
			uniform float mod6; 
			void main() {
				//gl_FragColor = vertex_color;
				//gl_FragColor = texture2D(texture, gl_FragCoord.xy/2.);// * 0.8;
				//gl_FragColor = texture2D(texture, vec2(44, 44));
				//  0.8;
				//gl_FragColor = texture2D(texture, gl_FragCoord.xy/128.) * 0.8;
				vec3 ray_end = vec3(texture2D(texture, vec2(gl_FragCoord.x/size.x, gl_FragCoord.y/size.y)));
				vec3 ray_start = vertex_color.xyz;
				float length = 0.;
				vec3 ray_dir = ray_end - ray_start;
				vec3 ray_delta = ray_dir / 200.;
				float ray_length = sqrt(ray_dir.x*ray_dir.x + ray_dir.y*ray_dir.y + ray_dir.z*ray_dir.z);
				vec3 pos = ray_start;
				float value = 0.;
				//mat3 direction_matrix = inverse(mat3(transpose(inverse(gl_ModelViewProjectionMatrix))));
				//mat3 direction_matrix = transpose(mat3(gl_ModelViewProjectionMatrix));
				//vec3 light_pos = (direction_matrix * vec3(-100.,100., -100)).zyx;
				//vec3 light_pos = (direction_matrix * vec3(-5.,5., -100));
				//vec3 origin = (direction_matrix * vec3(0., 0., 0)).xyz;
				vec3 origin = (vec4(0., 0., 0., 0.)).xyz;
				vec3 light_pos = (vec4(-1000., 0., -1000, 1.)).xyz;
				//mat3 mod = inverse(mat3(gl_ModelViewProjectionMatrix));
				vec4 color;
				vec3 light_dir = light_pos - origin;
				//light_dir = vec3(-1,-1,1);
				light_dir = light_dir / sqrt(light_dir.x*light_dir.x + light_dir.y*light_dir.y + light_dir.z*light_dir.z);
				float alpha_total = 0.;
				//float normalize = log(maxvalue);
				float intensity_total;
				for (int n = 0; n < 200; n++)  {
					//float fraction = float(n) / float(1000);
					//float z_depth = fraction*ray_length;
					//float current_value = texture3D(gradient, pos).b;
					//vec3 normal = texture3D(gradient, pos).zyx;
					//normal = normal/ sqrt(normal.x*normal.x + normal.y*normal.y + normal.z*normal.z);
					//float cosangle = -dot(light_dir, normal);
					float cosangle = 1.;
					//cosangle = clamp(cosangle, 0.0, 1.);;
					//float cosangle = 1.0;
					//float s = 0.0001;
					//value = value + current_value*exp(-(pow(pos.x - 0.5, 2)/s));//+pow(pos.y - 0.5, 2)/s+pow(pos.z - 0.5, 2)/s));
					//value = value + current_value;
					//*max(max(exp(-(pow(pos.x - 0.5, 2)/s)), exp(-(pow(pos.y - 0.5, 2)/s))), exp(-(pow(pos.z - 0.5, 2)/s)));
					//+pow(pos.y - 0.5, 2)/s+pow(pos.z - 0.5, 2)/s));
					
					float intensity = texture3D(cube, pos).r;
					float intensity_normalized = (log(intensity + 1.) - log(minmax3d.x)) / (log(minmax3d.y) - log(minmax3d.x));
					
					//intensity_normalized = clamp(cosangle, 0., 1.);
					vec4 color_sample = texture1D(texture_colormap, intensity_normalized);// * clamp(cosangle, 0.1, 1.);
					//color_sample = color_sample * clamp(cosangle, 0., 1.) * 15.;
					//color_sample = texture1D(texture_colormap, cosangle * 2. - 1.);
					float alpha_sample = 10./200. * alpha_mod  * intensity_normalized;// * clamp(cosangle+0.2, 0.0, 1.);;
					alpha_sample = clamp(alpha_sample, 0., 1.);
					
					
					intensity_total += intensity;
					
					
					color = color + (1.0 - alpha_total) * color_sample * alpha_sample;
					alpha_total = clamp(alpha_total + alpha_sample, 0., 1.);
					
					float border_level = log(minmax3d_total.x) + (log(minmax3d_total.y) - log(minmax3d_total.x)) * mod6 * 0.5;
					float alpha_sample_border = exp(-pow(border_level-log(intensity)/3.,2.)) * mod5;// * clamp(cosangle, 0.1, 1);

					float ambient = 0.5; //atan(log(mod4)) / 3.14159 + 0.5 ;
					vec4 color_border = vec4(1,1,1,1);// * (ambient + clamp(cosangle, 0, 1.-ambient));
					//vec4 color_border = vec4(normal.xyz, 1);// * clamp(cosangle, 0.1, 1);
					color = color + (1.0 - alpha_total) * color_border * alpha_sample_border;
					alpha_total = clamp(alpha_total + alpha_sample_border, 0., 1.);
					
					pos += ray_delta;
					
				}
				gl_FragColor = vec4(color) * mod4;// / pow(0.9*alpha_total + 0.1, 1.0); // / sqrt(color.r*color.r + color.b*color.b + color.g*color.g);
				//value *= 10;
				//gl_FragColor = vec4(ray_end, 1);
				//gl_FragColor = vec4(texture1D(texture_colormap, clamp(log(value*0.0001*ray_length+1)/log(10) * 1.2 - 0.1, 0.01, 0.99)).rgb, 1);
				//gl_FragColor = vec4(texture1D(texture_colormap, log(value*1.1+1.) ).rgb, 1);
				float scale = log(minmax2d.y)/log(10.) - log(minmax2d.x)/log(10.);
				float intensity_total_scaled = (log(intensity_total+1.)/log(10.)-log(minmax2d.x)/log(10.)) / scale;
				//scaled = value / 100.;
				vec4 line_color = vec4(texture1D(texture_colormap, intensity_total_scaled).rgb, 1);
				//gl_FragColor = line_color;
				//float blend = atan(log(mod5)) / 3.14159 + 0.5 ;
				//vec3 = gl_ModelViewProjectionMatrix
				//gl_FragColor = vec4(light_dir, 1.);
				//gl_FragColor = (blend * line_color + (1.-blend) * vec4(color)*mod6) * mod4;
				//gl_FragColor = vec4(value, 0, 0, 1);
				//gl_FragColor = texture3D(cube, vec3(gl_FragCoord.x/size.x, gl_FragCoord.y/size.y, 0.5) );
				//gl_FragColor = texture3D(gradient, vec3(gl_FragCoord.x/size.x, gl_FragCoord.y/size.y, 0.5) );
				//gl_FragColor = vec4(ray_start, 1);
			}""",GL_FRAGMENT_SHADER)
		self.fragment_shader = shaders.compileShader("""
			varying vec4 vertex_color;
			uniform sampler1D texture_colormap; 
			uniform sampler2D texture; 
			uniform sampler3D cube; 
			uniform sampler3D gradient;
			uniform vec2 size; // size of screen/fbo, to convert between pixels and uniform
			uniform vec2 minmax2d;
			uniform vec2 minmax3d;
			uniform vec2 minmax3d_total;
			//uniform float maxvalue2d;
			//uniform float maxvalue3d;
			uniform float alpha_mod; // mod3
			uniform float mod4;  // mafnifier
			uniform float mod5; // blend color and line integral
			uniform float mod6; 

			uniform float function_opacities[3];
			uniform float function_means[3];
			uniform float function_sigmas[3];
			
			uniform float brightness;
			
			
			void main() {
				int steps = 500;
				vec3 ray_end = vec3(texture2D(texture, vec2(gl_FragCoord.x/size.x, gl_FragCoord.y/size.y)));
				vec3 ray_start = vertex_color.xyz;
				float length = 0.;
				vec3 ray_dir = ray_end - ray_start;
				vec3 ray_delta = ray_dir / float(steps);
				float ray_length = sqrt(ray_dir.x*ray_dir.x + ray_dir.y*ray_dir.y + ray_dir.z*ray_dir.z);
				vec3 ray_pos = ray_start;
				float value = 0.;
				//mat3 direction_matrix = inverse(mat3(transpose(inverse(gl_ModelViewProjectionMatrix))));
				//mat3 direction_matrix = transpose(mat3(gl_ModelViewProjectionMatrix));
				//vec3 light_pos = (direction_matrix * vec3(-100.,100., -100)).zyx;
				//vec3 light_pos = (direction_matrix * vec3(-5.,5., -100));
				//vec3 origin = (direction_matrix * vec3(0., 0., 0)).xyz;
				vec3 origin = (vec4(0., 0., 0., 0.)).xyz;
				vec3 light_pos = (vec4(-1000., 0., -1000, 1.)).xyz;
				//mat3 mod = inverse(mat3(gl_ModelViewProjectionMatrix));
				vec4 color = vec4(0, 0, 0, 0);
				vec3 light_dir = light_pos - origin;
				//light_dir = vec3(-1,-1,1);
				light_dir = light_dir / sqrt(light_dir.x*light_dir.x + light_dir.y*light_dir.y + light_dir.z*light_dir.z);
				float alpha_total = 0.;
				//float normalize = log(maxvalue);
				float intensity_total;
				float data_min = minmax3d.x;
				float data_max = minmax3d.y;
				float data_scale = 1./(data_max - data_min);
				for(int i = 0; i < 500; i++) {
					vec4 sample = texture3D(cube, ray_pos);
					for(int j = 0; j < 3; j++) {
						float data_value = (sample.r - data_min) * data_scale;
						//float volume_level_value = (function_means[j] - data_min) * data_scale;
						float chi = (data_value-function_means[j])/function_sigmas[j];
						float chisq = pow(chi, 2.);
						float intensity = exp(-chisq);
						vec4 color_sample = texture1D(texture_colormap, data_value);// * clamp(cosangle, 0.1, 1.);
						float alpha_sample = function_opacities[j]*intensity * sign(data_value) * sign(1.-data_value) / float(steps) * 100.* ray_length ;//clamp(1.-chisq, 0., 1.) * 0.5;//1./128.* length(color_sample) * 100.;
						alpha_sample = clamp(alpha_sample, 0., 1.);
						color = color + (1.0 - alpha_total) * color_sample * alpha_sample;
						alpha_total = clamp(alpha_total + alpha_sample, 0., 1.);
						if(alpha_total >= 1.)
							break;
					}
					ray_pos += ray_delta;
				}
				gl_FragColor = vec4(color.rgb, alpha_total) * brightness; //brightness;
				//gl_FragColor = vec4(ray_pos.xyz, 1) * 100.; //brightness;
			}""",GL_FRAGMENT_SHADER)
		
		self.fragment_shader = shaders.compileShader("""
		#version 120
			varying vec4 vertex_color;
			uniform sampler1D texture_colormap; 
			uniform sampler2D texture; 
			uniform sampler3D cube; 
			uniform sampler3D gradient;
			uniform vec2 size; // size of screen/fbo, to convert between pixels and uniform
			uniform vec2 minmax2d;
			uniform vec2 minmax3d;
			uniform vec2 minmax3d_total;
			//uniform float maxvalue2d;
			//uniform float maxvalue3d;
			uniform float alpha_mod; // mod3
			uniform float mod4;  // mafnifier
			uniform float mod5; // blend color and line integral
			uniform float mod6; 

			uniform sampler1D transfer_function; 
			
			uniform float brightness;
			
			
			void main() {
				int steps = 300;
				vec3 ray_end = vec3(texture2D(texture, vec2(gl_FragCoord.x/size.x, gl_FragCoord.y/size.y)));
				vec3 ray_start = vertex_color.xyz;
				float length = 0.;
				vec3 ray_dir = ray_end - ray_start;
				vec3 ray_delta = ray_dir / float(steps);
				float ray_length = sqrt(ray_dir.x*ray_dir.x + ray_dir.y*ray_dir.y + ray_dir.z*ray_dir.z);
				vec3 ray_pos = ray_start;
				float value = 0.;
				//mat3 direction_matrix = inverse(mat3(transpose(inverse(gl_ModelViewProjectionMatrix))));
				mat3 mat_temp = mat3(gl_ModelViewProjectionMatrix[0].xyz, gl_ModelViewProjectionMatrix[1].xyz, gl_ModelViewProjectionMatrix[2].xyz);
				mat3 direction_matrix = mat_temp;
				vec3 light_pos = (vec3(-100.,100., -100) * direction_matrix).zyx;
				//vec3 light_pos = (direction_matrix * vec3(-5.,5., -100));
				//vec3 origin = (direction_matrix * vec3(0., 0., 0)).xyz;
				vec3 origin = (vec4(0., 0., 0., 0.)).xyz;
				//vec3 light_pos = (vec4(-1000., 0., -1000, 1.)).xyz;
				//mat3 mod = inverse(mat3(gl_ModelViewProjectionMatrix));
				vec4 color = vec4(0, 0, 0, 0);
				vec3 light_dir = light_pos - origin;
				mat3 rotation = mat3(gl_ModelViewMatrix);
				light_dir = vec3(-1,-1,1) * rotation;
				light_dir = normalize(light_dir);// / sqrt(light_dir.x*light_dir.x + light_dir.y*light_dir.y + light_dir.z*light_dir.z);
				float alpha_total = 0.;
				//float normalize = log(maxvalue);
				float intensity_total;
				float data_min = minmax3d.x;
				float data_max = minmax3d.y;
				float data_scale = 1./(data_max - data_min);
				float delta = 0.01/5.;
				//vec3 light_dir = vec3(1,1,-1);
				for(int i = 0; i < 300; i++) {
					/*vec3 normal = texture3D(gradient, ray_pos).zyx;
					normal = normal/ sqrt(normal.x*normal.x + normal.y*normal.y + normal.z*normal.z);
					float cosangle = dot(light_dir, normal);
					cosangle = clamp(cosangle, 0., 1.);*/

					vec4 sample = texture3D(cube, ray_pos);
					float sample_x = texture3D(cube, ray_pos + vec3(delta, 0, 0)).r;
					float sample_y = texture3D(cube, ray_pos + vec3(0, delta, 0)).r;
					float sample_z = texture3D(cube, ray_pos + vec3(0, 0, delta)).r;
					vec3 normal = normalize(-vec3((sample_x-sample.r)/delta, (sample_y-sample.r)/delta, (sample_z-sample.r)/delta));
					float cosangle = max(dot(light_dir, normal), 0.);

					float data_value = (sample.r - data_min) * data_scale;
					vec4 color_sample = texture1D(transfer_function, data_value);
					float change = abs((texture1D(transfer_function, data_value+delta).a - color_sample.a)/delta);

					//vec4 color_sample = texture1D(texture_colormap, data_value);// * clamp(cosangle, 0.1, 1.);
					float alpha_sample = color_sample.a * sign(data_value) * sign(1.-data_value) / float(steps) * 100.* ray_length; //function_opacities[j]*intensity * sign(data_value) * sign(1.-data_value) / float(steps) * 100.* ray_length ;//clamp(1.-chisq, 0., 1.) * 0.5;//1./128.* length(color_sample) * 100.;
					alpha_sample = clamp(alpha_sample, 0., 1.);
					color_sample = color_sample * (0.5 + 0.8*cosangle);
					//color_sample = vec4(normal, 1.);
					color = color + (1.0 - alpha_total) * color_sample * alpha_sample;
					alpha_total = clamp(alpha_total + alpha_sample, 0., 1.);
					if(alpha_total >= 1.)
						break;
					ray_pos += ray_delta;
				}
				gl_FragColor = vec4(color.rgb, alpha_total) * brightness; //brightness;
				//gl_FragColor = vec4(ray_pos.xyz, 1) * 100.; //brightness;
			}""",GL_FRAGMENT_SHADER)
		
		return shaders.compileProgram(self.vertex_shader, self.fragment_shader)

	def create_shader_vectorfield(self):
		self.vertex_shader_color = shaders.compileShader("""
			#extension GL_ARB_draw_instanced : enable
			varying vec4 vertex_color;
			void main() {
				float x = floor(float(gl_InstanceIDARB)/(8.*8.)) + 0.5;
				float y = mod(floor(float(gl_InstanceIDARB)/8.), 8.) + 0.5;
				float z = mod(float(gl_InstanceIDARB), 8.) + 0.5;
				vec4 pos = (gl_Vertex + vec4(x*80./8., y*80./8., z*80./8., 0));
				gl_Position = gl_ModelViewProjectionMatrix * pos;
				vertex_color =  pos /80. + vec4(0.5, 0.5, 0.5, 0.);
			}""",GL_VERTEX_SHADER)
		self.fragment_shader_color = shaders.compileShader("""
			varying vec4 vertex_color;
			void main() {
				gl_FragColor = vertex_color;
			}""",GL_FRAGMENT_SHADER)
		return shaders.compileProgram(self.vertex_shader_color, self.fragment_shader_color)

	def create_shader_vectorfield_color(self):
		self.vertex_shader_color = shaders.compileShader("""
		#version 120
			#extension GL_ARB_draw_instanced : enable
			varying vec4 vertex_color;
			uniform sampler3D vectorfield;
			uniform int grid_size;
			uniform int use_light;
			uniform vec3 light_color;
			uniform vec3 lightdir;
			uniform float count_level_min;
			uniform float count_level_max;

			void main() {
				float grid_size_f = float(grid_size);
				float x = floor(float(gl_InstanceIDARB)/(grid_size_f*grid_size_f))/grid_size_f;
				float y = mod(floor(float(gl_InstanceIDARB)/grid_size_f), grid_size_f)/grid_size_f;
				float z = mod(float(gl_InstanceIDARB), grid_size_f)/grid_size_f;
				vec3 uniform_center = vec3(x, y, z);
				vec4 sample = texture3D(vectorfield, uniform_center.yzx);
				vec3 velocity = sample.xyz;
				float counts = sample.a;
				float scale = (counts >= count_level_min) && (counts <= count_level_max) ? 1. : 0.0;
				float speed = length(velocity);
				vec3 direction = normalize(velocity) ;// / speed;
				// form two orthogonal vector to define a rotation matrix
				// the rotation around the vector's axis doesn't matter
				vec3 some_axis = normalize(vec3(0., 1., 1.));
				//vec3 some_axis2 = normalize(vec3(1., 0., 1.));
				vec3 axis1 = normalize(cross(direction, some_axis));
				// + (1-length(cross(direction, some_axis)))*cross(direction, some_axis2));
				vec3 axis2 = normalize(cross(direction, axis1));
				mat3 rotation_and_scaling = mat3(axis1, axis2, direction * (speed) /50);
				mat3 rotation_and_scaling_inverse_transpose = mat3(axis1, axis2, direction / (speed) /50);


				vec3 pos = gl_Vertex.xyz;//
				pos.z -= 0.5;
				pos *= scale;
				pos = rotation_and_scaling * pos;
				vec4 transformed_pos = vec4(pos + (uniform_center - vec3(0.5,0.5,0.5) + 1./grid_size_f/2.) * 80., 1);
				vertex_color =  transformed_pos/80. + vec4(0.5, 0.5, 0.5, 1.); //vec4(uniform_center + gl_ModelViewMatrix*pos, 0.);// + vec4(0.5, 0.5, 0.0, 1.);
				gl_Position = gl_ModelViewProjectionMatrix * transformed_pos;
				if(use_light == 1) {
					float fraction = 0.5;
					vec3 normal =  normalize(mat3(gl_ModelViewMatrix) * rotation_and_scaling_inverse_transpose * gl_Normal);
					//vec3 normal = normalize(gl_NormalMatrix * gl_Normal);
					//mat3 rotation = mat3(m);
					vec3 lightdir_t = normalize(lightdir);
					vertex_color = vec4(light_color * fraction + max(dot(lightdir_t, normal), 0.), 1.);
					//vertex_color = vec4(normal, 1.0); //vec4(lightdir_t, 1.);
				}

			}""",GL_VERTEX_SHADER)
		self.fragment_shader_color = shaders.compileShader("""
			varying vec4 vertex_color;
			void main() {
				gl_FragColor = vertex_color;
			}""",GL_FRAGMENT_SHADER)
		return shaders.compileProgram(self.vertex_shader_color, self.fragment_shader_color)

	def paintGL(self):
		if self.grid is not None:
			glMatrixMode(GL_MODELVIEW)

			glLoadIdentity()
			glTranslated(0.0, 0.0, -15.0)
			glRotated(self.orbit_angle, 0.0, 1.0, 0.0) 
			glRotated(self.angle1, 1.0, 0.0, 0.0)
			glRotated(self.angle2, 0.0, 1.0, 0.0)
			
			if self.grid is not None:
				self.draw_backside()
				self.draw_frontside()
				self.draw_to_screen()
			else:
				glViewport(0, 0, self.texture_size, self.texture_size)
				glBindFramebuffer(GL_FRAMEBUFFER, 0)
				glClearColor(0.0, 0.0, 0.0, 1.0)
				glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)

	def draw_backside(self):
		glViewport(0, 0, self.texture_size, self.texture_size)
		#glViewport(0, 0, 128*2, 128*2)
		glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
		glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.texture_backside, 0);
		glClearColor(1.0, 1.0, 0.0, 1.0)
		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
		
		glEnable(GL_DEPTH_TEST);
		
		glEnable(GL_CULL_FACE);
		glCullFace(GL_FRONT);

		glShadeModel(GL_SMOOTH);
		glUseProgram(self.shader_color)
		self.cube(size=80)
		self.cube(size=80, gl_type=GL_LINE_LOOP)
		glCullFace(GL_BACK);
		if 0:
			self.cube(size=10) # 'debug' cube
		#self.arrow(0.5, 0.5, 0.5, 80.0)
		#self.arrow_model.drawGL()
		glUseProgram(self.shader_vectorfield_color)
		if self.vectorgrid is not None:
			loc = glGetUniformLocation(self.shader_vectorfield_color, "vectorfield");
			glUniform1i(loc, 0); # texture unit 0
			loc = glGetUniformLocation(self.shader_vectorfield_color, "grid_size");
			glUniform1i(loc, self.vectorgrid.shape[0])
			loc = glGetUniformLocation(self.shader_vectorfield_color, "use_light");
			glUniform1i(loc, 0)
			mi, ma = np.nanmin(self.vectorgrid_counts), np.nanmax(self.vectorgrid_counts)
			#loc = glGetUniformLocation(self.shader_vectorfield_color, "count_level_min");
			#glUniform1f(loc, mi + (ma-mi) * self.min_level_vector3d)
			#loc = glGetUniformLocation(self.shader_vectorfield_color, "count_level_max");
			#glUniform1f(loc, mi + (ma-mi) * self.max_level_vector3d)

			loc = glGetUniformLocation(self.shader_vectorfield_color, "count_level_min");
			glUniform1f(loc, 10**(np.log10(ma)*self.min_level_vector3d))
			loc = glGetUniformLocation(self.shader_vectorfield_color, "count_level_max");
			glUniform1f(loc, 10**(np.log10(ma)*self.max_level_vector3d))

			glActiveTexture(GL_TEXTURE0);
			glEnable(GL_TEXTURE_3D)
			glBindTexture(GL_TEXTURE_3D, self.texture_cube_vector)
			self.arrow_model.drawGL(self.vectorgrid.shape[0]**3)
		glUseProgram(0)
		glActiveTexture(GL_TEXTURE0);
		glDisable(GL_TEXTURE_3D)
		#return
		
	def arrow(self, x, y, z, scale):
		headfraction = 0.4
		baseradius = 0.1 * scale
		headradius = 0.2 * scale
		
		# draw base
		glBegin(GL_QUADS)
		#glColor3f(1., 0., 0.)
		for part in range(10):
			angle = np.radians(part/10.*360)
			angle2 = np.radians((part+1)/10.*360)
			glNormal3f(np.cos(angle), np.sin(angle), 0.)
			glVertex3f(x+baseradius*np.cos(angle), y+baseradius*np.sin(angle), z+scale/2-headfraction*scale)
			glNormal3f(np.cos(angle), np.sin(angle), 0.)
			glVertex3f(x+baseradius*np.cos(angle), y+baseradius*np.sin(angle), z-scale/2)
			glNormal3f(np.cos(angle2), np.sin(angle2), 0.)
			glVertex3f(x+baseradius*np.cos(angle2), y+baseradius*np.sin(angle2), z-scale/2)
			glNormal3f(np.cos(angle2), np.sin(angle2), 0.)
			glVertex3f(x+baseradius*np.cos(angle2), y+baseradius*np.sin(angle2), z+scale/2-headfraction*scale)
		glEnd()
		glBegin(GL_TRIANGLE_FAN)
		glNormal3f(0, 0, -1)
		#glColor3f(0., 1., 0.)
		glVertex3f(x, y, z-scale/2)
		for part in range(10+1):
			angle = np.radians(-part/10.*360)
			glVertex3f(x+baseradius*np.cos(angle), y+baseradius*np.sin(angle), z-scale/2)
		glEnd()
		
		glBegin(GL_TRIANGLES)
		#glColor3f(0., 0., 1.)
		a = headradius - baseradius
		b = headfraction * scale
		headangle = np.arctan(a/b)
		for part in range(10+1):
			angle = np.radians(-part/10.*360)
			anglemid = np.radians(-(part+0.5)/10.*360)
			angle2 = np.radians(-(part+1)/10.*360)
			glNormal3f(np.cos(anglemid)*np.cos(headangle), np.sin(anglemid)*np.cos(headangle), np.sin(headangle))
			glVertex3f(x, y, z+scale/2)
			
			glNormal3f(np.cos(angle2)*np.cos(headangle), np.sin(angle2)*np.cos(headangle), np.sin(headangle))
			glVertex3f(x+headradius*np.cos(angle2), y+headradius*np.sin(angle2), z+scale/2-headfraction*scale)

			glNormal3f(np.cos(angle)*np.cos(headangle), np.sin(angle)*np.cos(headangle), np.sin(headangle))
			glVertex3f(x+headradius*np.cos(angle), y+headradius*np.sin(angle), z+scale/2-headfraction*scale)
		glEnd()

		glBegin(GL_QUADS)
		#glColor3f(1., 1., 0.)
		glNormal3f(0, 0, -1)
		for part in range(10):
			angle = np.radians(part/10.*360)
			angle2 = np.radians((part+1)/10.*360)
			glVertex3f(x+baseradius*np.cos(angle), y+baseradius*np.sin(angle), z+scale/2-headfraction*scale)
			glVertex3f(x+baseradius*np.cos(angle2), y+baseradius*np.sin(angle2), z+scale/2-headfraction*scale)
			glVertex3f(x+headradius*np.cos(angle2), y+headradius*np.sin(angle2), z+scale/2-headfraction*scale)
			glVertex3f(x+headradius*np.cos(angle), y+headradius*np.sin(angle), z+scale/2-headfraction*scale)
		glEnd()
		
		

	def draw_frontside(self):
		glViewport(0, 0, self.texture_size, self.texture_size)
		glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
		#glBindFramebuffer(GL_FRAMEBUFFER, 0)
		
		
		glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.texture_final, 0);
		
		
		glClearColor(1.0, 1.0, 1.0, 0.0)
		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
		
		glEnable(GL_CULL_FACE);
		glCullFace(GL_BACK);
		
		glShadeModel(GL_SMOOTH);
		
		glDisable(GL_BLEND)
		glColor3f(0, 0, 0)
		self.cube(size=80, gl_type=GL_LINE_LOOP) # draw the wireframe cube
		if 0:
			self.cube(size=10) # 'debug' cube
		glEnable(GL_LIGHTING);
		glEnable(GL_LIGHT0);
		g = 0.5
		glMaterialfv(GL_FRONT, GL_SPECULAR, [g, g, g, 1.]);
		glMaterialfv(GL_FRONT, GL_DIFFUSE, [g, g, g, 1.]);
		glPushMatrix()
		glLoadIdentity()
		#glLightfv(GL_LIGHT0, GL_POSITION, [1, -0.5, 1, 0.])
		glLightfv(GL_LIGHT0, GL_POSITION, [0.1, 0.1, 1, 0.])
		glPopMatrix()
		a = 0.5
		glLightfv(GL_LIGHT0, GL_AMBIENT, [a, a, a, 0.])
		glMaterialfv(GL_FRONT, GL_SHININESS, [50.]);
		glColorMaterial ( GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE )
		glEnable ( GL_COLOR_MATERIAL )
		glColor3f(0.5, 0, 0)
		#self.arrow(0.5, 0.5, 0.5, 80.0)
		if self.vectorgrid is not None:
			glUseProgram(self.shader_vectorfield_color)
			loc = glGetUniformLocation(self.shader_vectorfield_color, "vectorfield");
			glUniform1i(loc, 0); # texture unit 0
			loc = glGetUniformLocation(self.shader_vectorfield_color, "grid_size");
			glUniform1i(loc, self.vectorgrid.shape[0])
			loc = glGetUniformLocation(self.shader_vectorfield_color, "use_light");
			glUniform1i(loc, 1)
			loc = glGetUniformLocation(self.shader_vectorfield_color, "light_color");
			glUniform3f(loc, 1., 0., 0.);
			loc = glGetUniformLocation(self.shader_vectorfield_color, "lightdir");
			glUniform3f(loc, -1., -1., 1.);
			mi, ma = np.nanmin(self.vectorgrid_counts), np.nanmax(self.vectorgrid_counts)
			#loc = glGetUniformLocation(self.shader_vectorfield_color, "count_level_min");
			#//glUniform1f(loc, mi + (ma-mi) * self.min_level_vector3d)
			#glUniform1f(loc, 10**(log10(ma)*self.min_level_vector3d)
			#loc = glGetUniformLocation(self.shader_vectorfield_color, "count_level_max");
			#glUniform1f(loc, mi + (ma-mi) * self.max_level_vector3d)

			loc = glGetUniformLocation(self.shader_vectorfield_color, "count_level_min");
			glUniform1f(loc, 10**(np.log10(ma)*self.min_level_vector3d))
			loc = glGetUniformLocation(self.shader_vectorfield_color, "count_level_max");
			glUniform1f(loc, 10**(np.log10(ma)*self.max_level_vector3d))


			glActiveTexture(GL_TEXTURE0);
			glEnable(GL_TEXTURE_3D)
			glBindTexture(GL_TEXTURE_3D, self.texture_cube_vector)
			self.arrow_model.drawGL(self.vectorgrid.shape[0]**3)
			glDisable(GL_TEXTURE_3D)
		glUseProgram(0)
		glDisable(GL_LIGHTING);
		glDisable(GL_LIGHT0);
		glEnable(GL_BLEND)
		
		glBlendEquation(GL_FUNC_ADD, GL_FUNC_ADD)
		glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
		

		glUseProgram(self.shader)
		loc = glGetUniformLocation(self.shader, "texture");
		glUniform1i(loc, 0); # texture unit 0
		glBindTexture(GL_TEXTURE_2D, self.texture_backside)
		glEnable(GL_TEXTURE_2D)
		glActiveTexture(GL_TEXTURE0);
		
		
		loc = glGetUniformLocation(self.shader, "cube");
		glUniform1i(loc, 1); # texture unit 1
		glActiveTexture(GL_TEXTURE1);
		glBindTexture(GL_TEXTURE_3D, self.texture_cube)
		#glEnable(GL_TEXTURE_3D)

		loc = glGetUniformLocation(self.shader, "texture_colormap");
		glUniform1i(loc, 2); # texture unit 2
		glActiveTexture(GL_TEXTURE2);
		#index = gavi.vaex.colormaps.colormaps.index("afmhot")
		index = 16
		glBindTexture(GL_TEXTURE_1D, self.textures_colormap[index])
		glEnable(GL_TEXTURE_1D)

		if 1:
			loc = glGetUniformLocation(self.shader, "transfer_function");
			glUniform1i(loc, 3); # texture unit 3
			glActiveTexture(GL_TEXTURE3);
			#index = gavi.vaex.colormaps.colormaps.index("afmhot")
			glBindTexture(GL_TEXTURE_1D, self.texture_function)
			rgb = self.colormap_data[self.colormap_index]
			x = np.arange(self.texture_function_size) / (self.texture_function_size-1.)
			y = x * 0.
			for i in range(3):
				y += np.exp(-((x-self.function_means[i])/self.function_sigmas[i])**2) * self.function_opacities[i]
				#y +=np.exp(-((nx-self.function_means[i])/self.function_sigmas[i])**2) * (np.log10(self.function_opacities[i])+3)/3 * 32.
			print "max opacity", np.max(y)
			self.function_data[:,0] = rgb[:,0]
			self.function_data[:,1] = rgb[:,1]
			self.function_data[:,2] = rgb[:,2]
			self.function_data[:,3] = (y * 255).astype(np.uint8)
			self.function_data_1d = self.function_data.reshape(-1)
			glTexImage1D(GL_TEXTURE_1D, 0, GL_RGBA8, self.texture_function_size, 0, GL_RGBA, GL_UNSIGNED_BYTE, self.function_data_1d);
			
			glEnable(GL_TEXTURE_1D)
			
		if 0:
			loc = glGetUniformLocation(self.shader, "gradient");
			glUniform1i(loc, 4); # texture unit 4
			glActiveTexture(GL_TEXTURE4);
			glEnable(GL_TEXTURE_3D)
			glBindTexture(GL_TEXTURE_3D, self.texture_gradient)
				
		glActiveTexture(GL_TEXTURE0);
		
		size = glGetUniformLocation(self.shader,"size");
		glUniform2f(size, self.texture_size, self.texture_size);
		
		#maxvalue = glGetUniformLocation(self.shader,"maxvalue");
		#glUniform1f(maxvalue, self.data3d.max()*10**self.mod2);
		
		
		minmax = glGetUniformLocation(self.shader,"minmax2d");
		glUniform2f(minmax, 1*10**self.mod1, self.grid2d_max*10**self.mod2);

		minmax = glGetUniformLocation(self.shader,"minmax3d");
		xmin =  self.grid_min +  (self.grid_max -  self.grid_min) * self.min_level;
		xmax =  self.grid_min +  (self.grid_max -  self.grid_min) * self.max_level;
		glUniform2f(minmax, xmin, xmax);
		
		minmax3d_total = glGetUniformLocation(self.shader,"minmax3d_total");
		glUniform2f(minmax3d_total, self.grid_min, self.grid_max);
		
		glUniform1f(glGetUniformLocation(self.shader,"brightness"), self.brightness);
		
		glUniform1fv(glGetUniformLocation(self.shader,"function_means"), self.function_count, self.function_means);
		glUniform1fv(glGetUniformLocation(self.shader,"function_sigmas"), self.function_count, self.function_sigmas);
		glUniform1fv(glGetUniformLocation(self.shader,"function_opacities"), self.function_count, self.function_opacities);
		

		alpha_mod = glGetUniformLocation(self.shader,"alpha_mod");
		glUniform1f(alpha_mod , 10**self.mod3);
		
		for i in range(4,7):
			name = "mod" + str(i)
			mod = glGetUniformLocation(self.shader, name)
			glUniform1f(mod, 10**getattr(self, name));
		
		
		
		

		glShadeModel(GL_SMOOTH);
		self.cube(size=80) # do the volume rendering
		glUseProgram(0)

		glActiveTexture(GL_TEXTURE4);
		glBindTexture(GL_TEXTURE_3D, 0)
		glEnable(GL_TEXTURE_2D)

		glActiveTexture(GL_TEXTURE3);
		glBindTexture(GL_TEXTURE_1D, 0)
		glEnable(GL_TEXTURE_2D)

		glActiveTexture(GL_TEXTURE2);
		glBindTexture(GL_TEXTURE_1D, 0)
		glEnable(GL_TEXTURE_2D)

		glActiveTexture(GL_TEXTURE1);
		glBindTexture(GL_TEXTURE_2D, 0)
		glEnable(GL_TEXTURE_2D)

		glActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D, 0)
		glEnable(GL_TEXTURE_2D)

		glDisable(GL_BLEND)
		#return
		
	def draw_to_screen(self):
		w = self.width()
		h = self.height()
		glViewport(0, 0, w, h)
		#glShadeModel(GL_FLAT);
		
		glBindFramebuffer(GL_FRAMEBUFFER, 0)
		glClearColor(1.0, 0.0, 0.0, 1.0)
		glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
		
		glCullFace(GL_BACK);


		glBindTexture(GL_TEXTURE_2D, self.textures[self.texture_index % len(self.textures)])
		#glBindTexture(GL_TEXTURE_3D, self.texture_cube)
		glEnable(GL_TEXTURE_2D)
		glLoadIdentity()
		glBegin(GL_QUADS)
		w = 50
		z = -1
		glTexCoord2f(0,0); 
		glVertex3f(-w, -w, z)
		glTexCoord2f(1,0); 
		glVertex3f( w, -w, z)
		glTexCoord2f(1,1); 
		glVertex3f( w,  w, z)
		glTexCoord2f(0,1); 
		glVertex3f(-w,  w, z)
		glEnd()
		glBindTexture(GL_TEXTURE_2D, 0)
		
		#glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
		
	def draw_to_screen_(self):
		w = self.width()
		h = self.height()
		glViewport(0, 0, w, h)
		#glShadeModel(GL_FLAT);
		
		glBindFramebuffer(GL_FRAMEBUFFER, 0)
		glClearColor(0.0, 1.0, 0.0, 1.0)
		glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT)
		
		#glCullFace(GL_BACK);


		#glBindTexture(GL_TEXTURE_2D, self.textures[self.texture_index % len(self.textures)])
		glBindTexture(GL_TEXTURE_1D, 0)
		glBindTexture(GL_TEXTURE_2D, 0)
		glEnable(GL_TEXTURE_3D)
		glBindTexture(GL_TEXTURE_3D, self.texture_cube)
		glEnable(GL_TEXTURE_3D)
		glColor3f(1,0,0)
		glLoadIdentity()
		glBegin(GL_QUADS)
		w = 20
		z = -1
		glTexCoord3f(0,0, 0.5); 
		glVertex3f(-w, -w, z)
		glTexCoord3f(1,0, 0.5); 
		glVertex3f( w, -w, z)
		glTexCoord3f(1,1, 0.5); 
		glVertex3f( w,  w, z)
		glTexCoord3f(0,1, 0.5); 
		glVertex3f(-w,  w, z)
		glEnd()
		glBindTexture(GL_TEXTURE_3D, 0)
		
		#glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
		
		
	def cube(self, size, gl_type=GL_QUADS):
		w = size/2.
		
		def vertex(x, y, z):
			#glColor3f(x+w, y+w, z+w)
			#glMultiTexCoord3f(GL_TEXTURE1, x, y, z);
			glVertex3f(x, y, z)
		
		# back
		if 1:
			#glColor3f(1, 0, 0)
			glBegin(gl_type);
			vertex(-w, -w, -w)
			vertex(-w,  w, -w)
			vertex( w,  w, -w)
			vertex( w, -w, -w)
			glEnd()

		# front
		if 1:
			glBegin(gl_type);
			#glColor3f(0, 1, 0)
			vertex(-w, -w, w)
			vertex( w, -w, w)
			vertex( w,  w, w)
			vertex(-w,  w, w)
			glEnd()
		
		# right
		if 1:
			glBegin(gl_type);
			#glColor3f(0, 0, 1)
			vertex(w, -w,  w)
			vertex(w, -w, -w)
			vertex(w,  w, -w)
			vertex(w,  w,  w)
			glEnd()
		
		# left
		if 1:
			glBegin(gl_type);
			#glColor3f(0, 0, 1)
			vertex(-w, -w, -w)
			vertex(-w, -w,  w)
			vertex(-w,  w,  w)
			vertex(-w,  w, -w)
			glEnd()
		
		# top
		if 1:
			glBegin(gl_type);
			#glColor3f(0, 0, 1)
			vertex( w,  w, -w)
			vertex(-w,  w, -w)
			vertex(-w,  w,  w)
			vertex( w,  w,  w)
			glEnd()
		
		# bottom
		if 1:
			glBegin(gl_type);
			#glColor3f(0, 0, 1)
			vertex(-w, -w, -w)
			vertex( w, -w, -w)
			vertex( w, -w,  w)
			vertex(-w, -w,  w)
			glEnd()

	def resizeGL(self, w, h):
		glMatrixMode(GL_PROJECTION)
		glLoadIdentity()
		#glOrtho(-50, 50, -50, 50, -50.0, 50.0)
		glOrtho(-50, 50, -50, 50, -150.0, 150.0)
		glViewport(0, 0, w, h)
		
	def initializeGL(self):
		
		colormaps = gavi.vaex.colormaps.colormaps
		Nx, Ny = self.texture_function_size, 16
		self.colormap_data = np.zeros((len(colormaps), Nx, 3), dtype=np.uint8)
		
		import matplotlib.cm
		self.textures_colormap = glGenTextures(len(colormaps))
		for i, colormap_name in enumerate(colormaps):
			colormap = matplotlib.cm.get_cmap(colormap_name)
			mapping = matplotlib.cm.ScalarMappable(cmap=colormap)
			#pixmap = QtGui.QPixmap(32*2, 32)
			x = np.arange(Nx) / (Nx -1.)
			#x = np.vstack([x]*Ny)
			rgba = mapping.to_rgba(x,bytes=True).reshape(Nx, 4)
			rgb = rgba[:,0:3] * 1
			self.colormap_data[i] = rgb #(rgb*255.).astype(np.uint8)
			if i == 0:
				print rgb[0], rgb[-1], 
			
			
			texture = self.textures_colormap[i]
			glBindTexture(GL_TEXTURE_1D, texture)
			glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
			glTexImage1D(GL_TEXTURE_1D, 0, GL_RGB8, Nx, 0, GL_RGB, GL_UNSIGNED_BYTE, self.colormap_data[i]);
			#glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, self.texture_size, self.texture_size, 0, GL_RGBA, GL_UNSIGNED_BYTE, None);
			glBindTexture(GL_TEXTURE_1D, 0)
			
		if 1:
			self.texture_function = glGenTextures(1)
			texture = self.texture_function
			glBindTexture(GL_TEXTURE_1D, texture)
			glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
			self.function_data = np.zeros((self.texture_function_size, 4), dtype=np.uint8)
			x = np.arange(self.texture_function_size) * 255 / (self.texture_function_size-1.)
			self.function_data[:,0] = x
			self.function_data[:,1] = x
			self.function_data[:,2] = 0
			self.function_data[:,3] = x
			self.function_data_1d = self.function_data.reshape(-1)
			glTexImage1D(GL_TEXTURE_1D, 0, GL_RGBA8, Nx, 0, GL_RGBA, GL_UNSIGNED_BYTE, self.function_data_1d);
			#glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, self.texture_size, self.texture_size, 0, GL_RGBA, GL_UNSIGNED_BYTE, None);
			glBindTexture(GL_TEXTURE_1D, 0)

		if 1:
			N = 1024 * 4
			self.surface_data =  np.zeros((N, 3), dtype=np.uint8)
			self.texture_surface = glGenTextures(1)
			glBindTexture(GL_TEXTURE_1D, self.texture_surface)
			glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
			glTexParameteri(GL_TEXTURE_1D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
			glTexImage1D(GL_TEXTURE_1D, 0, GL_RGB8, Nx, 0, GL_RGB, GL_UNSIGNED_BYTE, self.surface_data);
			#glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, self.texture_size, self.texture_size, 0, GL_RGBA, GL_UNSIGNED_BYTE, None);
			glBindTexture(GL_TEXTURE_1D, 0)
			



		if 0:
			
			f = glCreateShaderObject(GL_FRAGMENT_SHADER);
			fragment_source = "void main(){ gl_FragColor=gl_FragCoord/512.0; }";
			glShaderSource(f, 1, fs, None);
			glCompileShaderARB(f);
		
			self.program = glCreateProgramObjectARB();
			glAttachObjectARB(self.program, f);

		
		#glClearColor(0.0, 0.0, 0.0, 1.0)
		#glClear(GL_COLOR_BUFFER_BIT)

		print bool(glGenFramebuffers)
		self.fbo = glGenFramebuffers(1)
		print self.fbo
		glBindFramebuffer(GL_FRAMEBUFFER, self.fbo)
		
		self.textures = self.texture_backside, self.texture_final = glGenTextures(2)
		print "textures", self.textures
		for texture in [self.texture_backside, self.texture_final]:
			glBindTexture(GL_TEXTURE_2D, texture)
			glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
			#glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
			#glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
			#glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA16F, self.texture_size, self.texture_size, 0, GL_RGBA, GL_FLOAT, None);
			glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, self.texture_size, self.texture_size, 0, GL_RGBA, GL_UNSIGNED_BYTE, None);
			glBindTexture(GL_TEXTURE_2D, 0)
			
		
		glFramebufferTexture2D(GL_FRAMEBUFFER_EXT, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, self.texture_backside, 0);

		self.render_buffer = glGenRenderbuffers(1);
		glBindRenderbuffer(GL_RENDERBUFFER, self.render_buffer);
		glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT, self.texture_size, self.texture_size);

		glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self.render_buffer);
		glBindFramebuffer(GL_FRAMEBUFFER, 0);
		#from matplotlib import pylab
		#pylab.imshow(np.log((self.data3d.astype(np.float32)).sum(axis=0)+1), cmap='PaulT_plusmin', origin="lower")
		#pylab.show()


		self.shader = self.create_shader()
		self.shader_color = self.create_shader_color()
		self.shader_vectorfield = self.create_shader_vectorfield()
		self.shader_vectorfield_color = self.create_shader_vectorfield_color()
		self.post_init()
			

	# only gavi specific code?
	def loadTable(self, args, column_names, grid_size=128, grid_size_vector=16):
		import gavi.dataset
		import gavifast
		dataset = gavi.dataset.load_file(sys.argv[1])
		x, y, z, vx, vy, vz = [dataset.columns[name] for name in sys.argv[2:]]
		x, y, z, vx, vy, vz = [k.astype(np.float64)-k.mean() for k in [x, y, z, vx, vy, vz]]
		grid3d = np.zeros((grid_size, grid_size, grid_size), dtype=np.float64)
		vectorgrid = np.zeros((4, grid_size_vector, grid_size_vector, grid_size_vector), dtype=np.float64)

		#mi, ma = -30., 30.
		#mi, ma = 45., 55
		#mi, ma = -20, 20
		s = 0.
		mi, ma = -4, 4
		print "histogram3d"
		gavifast.histogram3d(x, y, z, None, grid3d, mi+s, ma+s, mi, ma, mi, ma)
		if 0:
			vx = vx - vx.mean()
			vy = vy - vy.mean()
			vz = vz - vz.mean()
		gavifast.histogram3d(x, y, z, vx, vectorgrid[0], mi+s, ma+s, mi, ma, mi, ma)
		gavifast.histogram3d(x, y, z, vy, vectorgrid[1], mi+s, ma+s, mi, ma, mi, ma)
		gavifast.histogram3d(x, y, z, vz, vectorgrid[2], mi+s, ma+s, mi, ma, mi, ma)
		print vx
		print vectorgrid[0]
		print gavifast.resize(vectorgrid[0], 4)
		print gavifast.resize(vectorgrid[1], 4)
		print gavifast.resize(vectorgrid[2], 4)
		print gavifast.resize(grid3d, 4)
		print "$" * 80
		vectorgrid[3][:] = gavifast.resize(grid3d, grid_size_vector)
		for i in range(3):
			vectorgrid[i] /= vectorgrid[3] # go from weighted to mean

		if 1:
			vmax = max([np.nanmax(vectorgrid[0]), np.nanmax(vectorgrid[1]), np.nanmax(vectorgrid[2])])
			for i in range(3):
				vectorgrid[i] *= 1
		#self.data3d = self.data3d.astype(np.float32)
		#self.data2d = self.data2d.astype(np.float32)
		#self.size3d = 128 # * 4
		#self.data2d = np.zeros((self.size3d, self.size3d)) #.astype(np.float32)
		#
		#self.data2d

		#import scipy.ndimage
		##self.data3d = 10**scipy.ndimage.gaussian_filter(np.log10(self.data3d+1), 1.5)-1
		#self.data3d = 10**scipy.ndimage.gaussian_filter(np.log10(self.data3d+1), 0.5)-1
		#data3ds = scipy.ndimage.gaussian_filter((self.data3d), 1.5)
		vectorgrid = np.swapaxes(vectorgrid, 0, 3)
		
		self.setGrid(grid3d, vectorgrid)

			
	def setGrid(self, grid, vectorgrid=None):
		self.mod1 = 0
		self.mod2 = 0
		self.mod3 = 0
		self.mod4 = 0
		self.mod5 = 0
		self.mod6 = 0
		#self.grid = np.log10(grid.astype(np.float32)+1)
		if vectorgrid is not None:
			self.vectorgrid = vectorgrid.astype(np.float32)
			self.vectorgrid_counts = self.vectorgrid[:,:,:,3]
		else:
			self.vectorgrid = None
		self.grid = np.log10(grid.astype(np.float32)+1)
		self.grid_min, self.grid_max = np.nanmin(self.grid), np.nanmax(self.grid)
		grids_2d = [self.grid.sum(axis=i) for i in range(3)]
		self.grid2d_min, self.grid2d_max = min([np.nanmin(grid) for grid in grids_2d]), max([np.nanmax(grid) for grid in grids_2d])
		print "3d", self.grid_min, self.grid_max
		print "2d", self.grid2d_min, self.grid2d_max
		#return
		#data3ds = data3ds.sum(axis=0)
		if 0:
			self.grid_gradient = np.gradient(self.grid)
			length = np.sqrt(self.grid_gradient[0]**2 + self.grid_gradient[1]**2 + self.grid_gradient[2]**2)
			self.grid_gradient[0] = self.grid_gradient[0] / length
			self.grid_gradient[1] = self.grid_gradient[1] / length
			self.grid_gradient[2] = self.grid_gradient[2] / length

			self.grid_gradient_data = np.zeros(self.grid.shape + (3,), dtype=np.float32)
			self.grid_gradient_data[:,:,:,0] = self.grid_gradient[0]
			self.grid_gradient_data[:,:,:,1] = self.grid_gradient[1]
			self.grid_gradient_data[:,:,:,2] = self.grid_gradient[2]
			self.grid_gradient_data[:,:,:,2] = 1.
			self.grid_gradient = self.grid_gradient_data
			del self.grid_gradient_data
			print self.grid_gradient.shape
		
		
		#self.data3d -= self.data3d.min()
		#self.data3d /= self.data3d.max()
		#self.data3d = np.log10(self.data3d+1)
		#self.data2d = np.log10(self.data2d+1)

		#self.data3df = (self.data3d * 1.).astype(np.float32)
		#self.data2df = self.data2d * 1.0
		
		#self.data3d -= self.data3d.min()
		#self.data3d /= self.data3d.max()
		#self.data3d = (self.data3d * 255).astype(np.uint8)

		#self.data2d -= self.data2d.min()
		#self.data2d /= self.data2d.max()
		#self.data2d = (self.data2d * 255).astype(np.uint8)
		#print self.data3d.max()
		for texture in [self.texture_cube, self.texture_gradient]:
			if texture is not None:
				glDeleteTextures(texture)

		self.texture_cube = glGenTextures(1)
		self.texture_gradient = glGenTextures(1)
		#self.texture_square = glGenTextures(1)
		
		#glActiveTexture(GL_TEXTURE1);
		#glBindTexture(GL_TEXTURE_3D, self.texture_cube)
		#glBindTexture(GL_TEXTURE_3D, self.texture_cube)
		#glBindTexture(GL_TEXTURE_2D, self.texture_square)
		#glTexImage3D(GL_TEXTURE_3D, 0, GL_LUMINANCE8, self.size3d, self.size3d, self.size3d, 0,
         #               GL_RED, GL_FLOAT, self.data3d)

		if 0:
			self.rgb3d = np.zeros(self.grid.shape + (3,), dtype=np.uint8)
			self.rgb3d[:,:,:,0] = self.grid
			self.rgb3d[:,:,:,1] = self.grid
			self.rgb3d[:,:,:,2] = self.grid

		glBindTexture(GL_TEXTURE_3D, self.texture_cube)
		width, height, depth = self.grid.shape[::-1]
		print "dims", width, height, depth
		glTexImage3D(GL_TEXTURE_3D, 0, GL_R32F, width, height, depth, 0,
					GL_RED, GL_FLOAT, self.grid)
		#print self.grid, self.texture_cube
		#glTexImage3D(GL_TEXTURE_3D, 0, GL_RGB8, self.size3d, self.size3d, self.size3d, 0,
         #               GL_RGB, GL_UNSIGNED_BYTE, self.rgb3d)
		
		glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);
		glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
		glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
		if 1:
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER);
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_R, GL_CLAMP_TO_BORDER);
		glBindTexture(GL_TEXTURE_3D, 0)
			
		if self.vectorgrid is not None:
			#print self.vectorgrid
			#print "counts", self.vectorgrid[3]
			assert self.vectorgrid.shape[0] == self.vectorgrid.shape[1] == self.vectorgrid.shape[2], "wrong shape %r" %  self.vectorgrid.shape
			self.texture_cube_vector_size = self.vectorgrid.shape[0]
			self.texture_cube_vector = glGenTextures(1)
			glBindTexture(GL_TEXTURE_3D, self.texture_cube_vector)
			_, width, height, depth = self.vectorgrid.shape[::-1]
			print "dims vector", width, height, depth
			glTexImage3D(GL_TEXTURE_3D, 0, GL_RGBA32F, width, height, depth, 0,
						GL_RGBA, GL_FLOAT, self.vectorgrid)
			print self.grid, self.texture_cube
			#glTexImage3D(GL_TEXTURE_3D, 0, GL_RGB8, self.size3d, self.size3d, self.size3d, 0,
			#               GL_RGB, GL_UNSIGNED_BYTE, self.rgb3d)
			
			glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_R, GL_CLAMP_TO_EDGE);
			glBindTexture(GL_TEXTURE_3D, 0)
				
			

		# gradient
		if 0:
			glBindTexture(GL_TEXTURE_3D, self.texture_gradient)
			glTexImage3D(GL_TEXTURE_3D, 0, GL_RGB32F, width, height, depth, 0,
							GL_RGB, GL_FLOAT, self.grid_gradient)
			#glTexImage3D(GL_TEXTURE_3D, 0, GL_RGB8, self.size3d, self.size3d, self.size3d, 0,
			#               GL_RGB, GL_UNSIGNED_BYTE, self.rgb3d)
			
			glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
			glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
			if 1:
				glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
				glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
				glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);
				glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER);
				glTexParameteri(GL_TEXTURE_3D, GL_TEXTURE_WRAP_R, GL_CLAMP_TO_BORDER);
			glBindTexture(GL_TEXTURE_3D, 0)
			
		if 0:
			import pylab
			pylab.subplot(221)
			pylab.imshow(np.log10(grids_2d[0]+1))
			pylab.subplot(222)
			pylab.imshow(np.log10(grids_2d[1]+1))
			pylab.subplot(223)
			pylab.imshow(np.log10(grids_2d[2]+1))
			pylab.subplot(224)
			pylab.imshow(np.log10(self.grid[128]+1))
			pylab.show()
		self.update()
		
			
		
		

			#glTexParameteri(GL_TEXTURE_2D, GL_GENERATE_MIPMAP, GL_TRUE)

	#sys.exit(0)
		#self.back_buffer, self.final_buffer = glGenTextures(2)
		#bo = glGenFramebuffers(1)


	def mouseMoveEvent(self, event):
		x, y = event.x(), event.y()
		dx = x - self.mouse_x
		dy = y - self.mouse_y
		
		
		speed = 1.
		speed_mod = 0.1/5./5.
		if self.mouse_button_down:
			self.angle2 += dx * speed
			self.angle1 += dy * speed
			print self.angle1, self.angle2
		if self.mouse_button_down_right:
			if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.NoModifier:
				self.min_level += dx * speed_mod / 10.
				self.max_level += -dy * speed_mod / 10.
				print "mod1/2", self.min_level, self.max_level
			if (QtGui.QApplication.keyboardModifiers() == QtCore.Qt.AltModifier) or (QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ControlModifier):
				self.mod3 += dx * speed_mod
				self.mod4 += -dy * speed_mod
				print "mod3/4", self.mod3, self.mod4
			if QtGui.QApplication.keyboardModifiers() == QtCore.Qt.ShiftModifier:
				self.mod5 += dx * speed_mod
				self.mod6 += -dy * speed_mod
				print "mod5/6", self.mod5, self.mod6
			
		
		self.mouse_x, self.mouse_y = x, y
		if self.mouse_button_down or self.mouse_button_down_right:
			self.update()
		
	def mousePressEvent(self, event):
		if event.button() == QtCore.Qt.LeftButton:
			self.mouse_button_down = True
		if event.button() == QtCore.Qt.RightButton:
			self.mouse_button_down_right = True

	def mouseReleaseEvent(self, event):
		if event.button() == QtCore.Qt.LeftButton:
			self.mouse_button_down = False
		if event.button() == QtCore.Qt.RightButton:
			self.mouse_button_down_right = False
			
	def write(self):
		colormap_name = "afmhot"
		import matplotlib.cm
		colormap = matplotlib.cm.get_cmap(colormap_name)
		mapping = matplotlib.cm.ScalarMappable(cmap=colormap)
		#pixmap = QtGui.QPixmap(32*2, 32)
		data = np.zeros((128*8, 128*16, 4), dtype=np.uint8)
		
		mi, ma = 1*10**self.mod1, self.data3d.max()*10**self.mod2
		intensity_normalized = (np.log(self.data3d + 1.) - np.log(mi)) / (np.log(ma) - np.log(mi));
		import PIL.Image
		for y2d in range(8):
			for x2d in range(16):
				zindex = x2d + y2d*16
				I = intensity_normalized[zindex]
				rgba = mapping.to_rgba(I,bytes=True) #.reshape(Nx, 4)
				print rgba.shape
				subdata = data[y2d*128:(y2d+1)*128, x2d*128:(x2d+1)*128]
				for i in range(3):
					subdata[:,:,i] = rgba[:,:,i]
				subdata[:,:,3] = (intensity_normalized[zindex]*255).astype(np.uint8)
				if 0:
					filename = "cube%03d.png" % zindex
					img = PIL.Image.frombuffer("RGB", (128, 128), subdata[:,:,0:3] * 1)
					print "saving to", filename
					img.save(filename)
		img = PIL.Image.frombuffer("RGBA", (128*16, 128*8), data)
		filename = "cube.png"
		print "saving to", filename
		img.save(filename)
		
		filename = "colormap.png"
		print "saving to", filename
		height, width = self.colormap_data.shape[:2]
		img = PIL.Image.frombuffer("RGB", (width, height), self.colormap_data)
		img.save(filename)
		
		

class TestWidget(QtGui.QMainWindow):
	def __init__(self, parent):
		super(TestWidget, self).__init__(parent)
		self.resize(700, 700)
		self.show()
		self.raise_()
		shortcut = QtGui.QShortcut(QtGui.QKeySequence("Cmd+Q"), self)
		shortcut.activated.connect(self.myclose)
		
		self.main = VolumeRenderWidget(self)
		self.setCentralWidget(self.main)
		
		#self.layout = QtGui.QVBoxLayout(self)
		#self.layout.addWidget(self.main)
		#self.setLayout(self.layout)
		
	def myclose(self, ignore=None):
		self.hide()
		

from OpenGL.arrays import vbo

class Arrow(object):
	def begin(self, type):
		self.type = type
		
	def end(self):
		self.offset = len(self.vertices)
	
	def vertex3f(self, x, y, z):
		self.vertices.append([x,y,z])
		self.normals.append(list(self.current_normal))
	
	def normal3f(self, x, y, z):
		self.current_normal = [x, y, z]
		
	def tri(self, i1, i2, i3):
		self.indices.append(self.offset + i1)
		self.indices.append(self.offset + i2)
		self.indices.append(self.offset + i3)
		
	def drawGL(self, instances=1):
		glEnableClientState(GL_VERTEX_ARRAY)
		glEnableClientState(GL_NORMAL_ARRAY)
		vertices_ptr = self.vertices.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
		glVertexPointer(3, GL_FLOAT, 0, vertices_ptr);
		normal_ptr = self.normals.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
		glNormalPointer(GL_FLOAT, 0, normal_ptr);
		indices_ptr = self.indices.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
		#glDrawElements(GL_TRIANGLES, len(self.indices), GL_UNSIGNED_INT, indices_ptr);
		glDrawElementsInstanced(GL_TRIANGLES, len(self.indices), GL_UNSIGNED_INT, indices_ptr, instances);
		glDisableClientState(GL_VERTEX_ARRAY);
		glDisableClientState(GL_NORMAL_ARRAY);
		
		
	def __init__(self, x, y, z, scale=80, headfraction=0.4, baseradius=0.1, headradius=0.2):
		self.vertices = []
		self.normals = []
		self.indices = []
		self.offset = 0
		
		headfraction = 0.5
		baseradius = 0.1 * scale/1.5
		headradius = 0.2 * scale
		
		# draw base
		self.begin(GL_QUADS)
		#glColor3f(1., 0., 0.)
		parts = 10
		for part in range(parts):
			angle = np.radians(part/10.*360)
			angle2 = np.radians((part+1)/10.*360)
			self.normal3f(np.cos(angle), np.sin(angle), 0.)
			self.vertex3f(x+baseradius*np.cos(angle), y+baseradius*np.sin(angle), z+scale/2-headfraction*scale)
			self.normal3f(np.cos(angle), np.sin(angle), 0.)
			self.vertex3f(x+baseradius*np.cos(angle), y+baseradius*np.sin(angle), z-scale/2)
			
			#self.normal3f(np.cos(angle2), np.sin(angle2), 0.)
			#self.vertex3f(x+baseradius*np.cos(angle2), y+baseradius*np.sin(angle2), z-scale/2)
			#self.normal3f(np.cos(angle2), np.sin(angle2), 0.)
			#self.vertex3f(x+baseradius*np.cos(angle2), y+baseradius*np.sin(angle2), z+scale/2-headfraction*scale)
			
		for part in range(10+1):
			self.tri((part*2+0) % (10*2), (part*2+1) % (10*2), (part*2+2) % (10*2))
			self.tri((part*2+2) % (10*2), (part*2+1) % (10*2), (part*2+3) % (10*2))
		self.end()

		# end of base
		self.begin(GL_TRIANGLE_FAN)
		self.normal3f(0, 0, -1)
		#glColor3f(0., 1., 0.)
		for part in range(10):
			angle = np.radians(-part/10.*360)
			self.vertex3f(x+baseradius*np.cos(angle), y+baseradius*np.sin(angle), z-scale/2)
		self.vertex3f(x, y, z-scale/2)
		for part in range(parts+1):
			self.tri(parts, part, (part+1) % (parts))
		self.end()

		#glColor3f(0., 0., 1.)
		# head
		a = headradius - baseradius
		b = headfraction * scale
		headangle = np.arctan(a/b)
		for part in range(10+1):
			self.begin(GL_TRIANGLES)
			angle = np.radians(-part/10.*360)
			anglemid = np.radians(-(part+0.5)/10.*360)
			angle2 = np.radians(-(part+1)/10.*360)
			self.normal3f(np.cos(anglemid)*np.cos(headangle), np.sin(anglemid)*np.cos(headangle), np.sin(headangle))
			self.vertex3f(x, y, z+scale/2)
			
			self.normal3f(np.cos(angle2)*np.cos(headangle), np.sin(angle2)*np.cos(headangle), np.sin(headangle))
			self.vertex3f(x+headradius*np.cos(angle2), y+headradius*np.sin(angle2), z+scale/2-headfraction*scale)

			self.normal3f(np.cos(angle)*np.cos(headangle), np.sin(angle)*np.cos(headangle), np.sin(headangle))
			self.vertex3f(x+headradius*np.cos(angle), y+headradius*np.sin(angle), z+scale/2-headfraction*scale)
			self.tri(0, 1, 2)
			self.end()


		# connecting base and head
		self.begin(GL_QUADS)
		#glColor3f(1., 1., 0.)
		self.normal3f(0, 0, -1)
		for part in range(10):
			angle = np.radians(-part/10.*360)
			angle2 = np.radians(-(part+1)/10.*360)
			self.vertex3f(x+baseradius*np.cos(angle), y+baseradius*np.sin(angle), z+scale/2-headfraction*scale)
			self.vertex3f(x+headradius*np.cos(angle), y+headradius*np.sin(angle), z+scale/2-headfraction*scale)
			#self.vertex3f(x+baseradius*np.cos(angle2), y+baseradius*np.sin(angle2), z+scale/2-headfraction*scale)
			#self.vertex3f(x+headradius*np.cos(angle2), y+headradius*np.sin(angle2), z+scale/2-headfraction*scale)
		for part in range(10+1):
			self.tri((part*2+0) % (10*2), (part*2+1) % (10*2), (part*2+2) % (10*2))
			self.tri((part*2+2) % (10*2), (part*2+1) % (10*2), (part*2+3) % (10*2))
		self.end()

		self.vertices = np.array(self.vertices, dtype=np.float32)
		self.normals = np.array(self.normals, dtype=np.float32)
		self.indices = np.array(self.indices, dtype=np.uint32)
	
		
if __name__ == "__main__":
	import gavi.vaex.colormaps
	colormaps = gavi.vaex.colormaps.colormaps
	import json
	js = json.dumps(gavi.vaex.colormaps.colormaps)
	print js

	app = QtGui.QApplication(sys.argv)
	widget = TestWidget(None)
	def load():
		widget.main.loadTable(sys.argv[1], sys.argv[2:])
	widget.main.post_init = load
	sys.exit(app.exec_())
function svgcontrols(){

    // XXX set up for unique ID's so can have multiple maps?
    // XXX test on other devices

    // the key elements
    var svge = document.getElementById('nexusmap');
    var viewe = document.getElementById('viewcontrol');

    // catch all events on Safari:
    var backe = document.createElementNS("http://www.w3.org/2000/svg",'rect');
    backe.setAttribute("id","eventcatcher")
    backe.setAttribute("x","0");
    backe.setAttribute("y","0");
    backe.setAttribute("width","1");
    backe.setAttribute("height","1");
    backe.setAttribute("style","fill:none;");
    backe.setAttribute("pointer-events","none");
    //backe.setAttribute("focusable","true");
    svge.appendChild(backe);

    var Smax = 100;
    var Smin = 0.5;
    var zoomSensitivity = 0.02;

    var mode = '';
    var X0i, Y0i ,X1i ,Y1i ,X0f ,Y0f ,X1f ,Y1f ,Di ,Df ,cXi ,cYi ,cXf ,cYf;
    var startScale = 1.0;

    // --------------------------------------------------------------------------
    // Misc
    // --------------------------------------------------------------------------
    function resetBack(){
        // Get's around Safari not capturing events on background of svg element
        // by setting a transparent rect the same size as the viewbox
        backe.width.baseVal.value = svge.getBoundingClientRect().width;
        backe.height.baseVal.value = svge.getBoundingClientRect().height;
    }

    function setCTM(element, m) {
        var s = "matrix(" + m.a + "," + m.b + "," + m.c + "," + m.d + "," + m.e + "," + m.f + ")";
        element.setAttributeNS(null, "transform", s);
    };

    // --------------------------------------------------------------------------
    // Fit map to area
    // --------------------------------------------------------------------------
    function fit(){
        var sr = svge.getBoundingClientRect();
        var vr = viewe.getBoundingClientRect();

        var cx = (vr.left+vr.right)/2.0;
        var cy = (vr.top+vr.bottom)/2.0;
        var dx = (sr.left+sr.right)/2.0-cx;
        var dy = (sr.top+sr.bottom)/2.0-cy;

        zoom( 0.9*Math.min( sr.height/vr.height, sr.width/vr.width ), cx, cy );

        pan(dx,dy);
 
    }

    // --------------------------------------------------------------------------
    // Pan map
    // --------------------------------------------------------------------------
    function pan(dx, dy){       

        var s = viewe.getCTM().a;

        var sr = svge.getBoundingClientRect();
        var vr = viewe.getBoundingClientRect();
        var pad = 20;

        // limit pan so fig doesn't totally fly off
        if (dx > 0 && vr.left+dx/s > sr.right-pad) {
            dx = sr.right-pad-vr.left;
        }
         if (dx < 0 && vr.right+dx/s < sr.left+pad) {
            dx = sr.left+pad-vr.right;
        }
        if (dy > 0 && vr.top+dy/s > sr.bottom-pad) {
            dy = sr.bottom-pad-vr.top;
        }
         if (dy < 0 && vr.bottom+dy/s < sr.top+pad) {
            dy = sr.top+pad-vr.bottom;
        }
       
        var zoomMat = svge.createSVGMatrix()
                    .translate(dx/s, dy/s);

        setCTM(viewe, viewe.getCTM().multiply(zoomMat));
    };

    // --------------------------------------------------------------------------
    // Zoom map
    // --------------------------------------------------------------------------
    function zoom(scale, x0,y0){

        var p = svge.createSVGPoint();
        var sr = svge.getBoundingClientRect();

        // this is the position relative to the top-left of svg
        // the precise offsets matter only for this function 
        p.x = x0-sr.left; 
        p.y = y0-sr.top;

        p = p.matrixTransform( viewe.getCTM().inverse() );

        var origMat = viewe.getCTM();

        if (origMat.a*scale >= Smin && origMat.a*scale <= Smax){
            newscale = scale;
        } else {
            newscale = 1.0;
        }

        var zoomMat = svge.createSVGMatrix()
                .translate(p.x, p.y)
                .scale(newscale)
                .translate(-p.x, -p.y);

        setCTM(viewe, origMat.multiply(zoomMat));

    };

    // --------------------------------------------------------------------------
    // Wheel Event
    // --------------------------------------------------------------------------
    svge.addEventListener('wheel', function(evt){
        //console.log("wheel["+evt.deltaX+", "+evt.deltaY+" ctrl: "+evt.ctrlKey+"]");
        resetBack();
        evt.preventDefault();

        if (evt.ctrlKey) {
            var z = Math.exp(-evt.deltaY*zoomSensitivity);
            zoom(z, evt.clientX, evt.clientY)
        }
        else {
            pan(-evt.deltaX, -evt.deltaY);
        }
    }, false);

    // --------------------------------------------------------------------------
    // Mouse Events
    // --------------------------------------------------------------------------
    svge.addEventListener('mousedown', function(evt){
        //console.log("mousedown");
        resetBack();
        if (mode=='') {
            mode = 'dragging';
            X0i = evt.clientX;
            Y0i = evt.clientY;
        }
    }, false);

    svge.addEventListener('mousemove', function(evt){
        //console.log("mousemove");
        if (mode=='dragging'){
            X0f = evt.clientX;
            Y0f = evt.clientY;
            pan(X0f-X0i, Y0f-Y0i)
            X0i = X0f;
            Y0i = Y0f;
        }
    }, false);

    svge.addEventListener('mouseup', function(evt){
        //console.log("mouseup");
        if (mode=='dragging'){
            mode = '';
        }
    }, false);

    // put this on the window to catch events where mouse leaves svg before leaving
    window.addEventListener('mouseup', function(evt){
        mode = '';
    })

    // --------------------------------------------------------------------------
    // Touch Events
    // --------------------------------------------------------------------------
    svge.addEventListener('touchstart', function(evt){
        //console.log("touchstart");
        mode = '';
        resetBack();

        if (evt.touches.length == 1) {
            mode = 'panning';
            X0i = evt.touches[0].clientX;
            Y0i = evt.touches[0].clientY;
        }
        else if (evt.touches.length == 2) {
            mode = 'zooming';
            X0i = evt.touches[0].clientX;
            Y0i = evt.touches[0].clientY;
            X1i = evt.touches[1].clientX;
            Y1i = evt.touches[1].clientY;
            startScale = viewe.getCTM().a;
            cXi = ((X0i + X1i) / 2.0);
            cYi = ((Y0i + Y1i) / 2.0);
            Di = Math.sqrt( Math.pow((X1i-X0i),2) + Math.pow((Y1i-Y0i),2) );
            startScale = 1.0;
        }
        
    }, false);

    svge.addEventListener('touchmove', function(evt){
        //console.log("touchmove");
        evt.preventDefault();

        if ( mode == 'panning') {
            X0f = evt.touches[0].clientX;
            Y0f = evt.touches[0].clientY;
            pan(X0f-X0i, Y0f-Y0i)
            X0i = X0f;
            Y0i = Y0f;
        }
        else if ( mode == 'zooming') {
            X0f = evt.touches[0].clientX;
            Y0f = evt.touches[0].clientY;
            X1f = evt.touches[1].clientX;
            Y1f = evt.touches[1].clientY;

            cXf = ((X0f + X1f) / 2.0);
            cYf = ((Y0f + Y1f) / 2.0);
            //pan(cXf-cXi, cYf-cYi)

            Df = Math.sqrt( Math.pow((X1f-X0f),2) + Math.pow((Y1f-Y0f),2) );

            var scale = Df/Di;
            zoom(scale/startScale, cXf, cYf);

            //pan(cXf-cXi, cYf-cYi);

            X0i = X0f;
            Y0i = Y0f;
            X1i = X1f;
            Y1i = Y1f;

            startScale = scale;
        }

    }, false);

    svge.addEventListener('touchleave', function(evt){
        //console.log("touchleave");
        mode = '';
        startScale = 1.0;
    }, false);

    // --------------------------------------------------------------------------
    // Key Events
    // --------------------------------------------------------------------------
    //svge.addEventListener('keypress', function(evt){
    //    if (evt.keyCode==189){
    //        // -
    //        zoom(0.9, 0, 0);
    //    }
    //    if (evt.keyCode==187){
    //        // = (+)
    //        zoom(1.1, 0, 0);
    //    }
//
    //}, false);

    // --------------------------------------------------------------------------
    // Initialise
    // --------------------------------------------------------------------------
    resetBack();
    fit();

}

svgcontrols();